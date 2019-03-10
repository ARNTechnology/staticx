import os
import logging
import shutil
import tempfile

from ..elf import get_shobj_deps
from ..utils import make_executable, mkdirs_for

def process_pyinstaller_archive(sx_ar, prog):
    # See utils/cliutils/archive_viewer.py

    # If PyInstaller is not installed, do nothing
    try:
        from PyInstaller.archive.readers import CArchiveReader, NotAnArchiveError
    except ImportError:
        return

    # Attempt to open the program as PyInstaller archive
    try:
        pyi_ar = CArchiveReader(prog)
    except:
        # Silence all PyInstaller exceptions here
        return
    logging.info("Opened PyInstaller archive!")

    with PyInstallHook(sx_ar, pyi_ar) as h:
        h.process()



class PyInstallHook(object):

    def __init__(self, sx_archive, pyi_archive):
        self.sx_ar = sx_archive
        self.pyi_ar = pyi_archive

        # Create a temporary directory
        # TODO PY3: Use tempfile.TemporaryDirectory and cleanup()
        self.tmpdir = tempfile.mkdtemp(prefix='staticx-pyi-')


    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        shutil.rmtree(self.tmpdir)


    def process(self):
        libs = self._extract_binaries()
        for lib in libs:
            self._add_required_deps(lib)


    def _extract_binaries(self):
        result = []

        for n, item in enumerate(self.pyi_ar.toc.data):
            (dpos, dlen, ulen, flag, typcd, name) = item

            # Only process binary files
            # See xformdict in PyInstaller.building.api.PKG
            if typcd != 'b':
                continue

            # Extract it to a temporary location
            _, data = self.pyi_ar.extract(n)
            tmppath = os.path.join(self.tmpdir, name)
            logging.debug("Extracting to {}".format(tmppath))
            mkdirs_for(tmppath)
            with open(tmppath, 'wb') as f:
                f.write(data)

            # We can't use yield here, because we need all of the libraries to be
            # extracted prior to running ldd (see #61)
            result.append(tmppath)

        return result


    def _add_required_deps(self, lib):
        """Add dependencies of lib to staticx archive"""

        # Silence "you do not have execution permission" warning from ldd
        make_executable(lib)

        # Add any missing libraries to our archive
        for deppath in get_shobj_deps(lib, libpath=[self.tmpdir]):
            dep = os.path.basename(deppath)

            if dep in self.sx_ar.libraries:
                logging.debug("{} already in staticx archive".format(dep))
                continue

            if self.pyi_ar.toc.find(dep) != -1:
                logging.debug("{} already in pyinstaller archive".format(dep))
                continue

            logging.debug("Adding {} to archive".format(dep))
            self.sx_ar.add_library(deppath)
