from gub import target
from gub import tools

class Libgd (target.AutoBuild):
    source = 'http://www.libgd.org/releases/gd-2.0.36RC1.tar.gz'
    def _get_build_dependencies (self):
        return [
            'tools::libtool',
            'fontconfig',
            'freetype',
            'libjpeg',
            'libpng',
            'zlib',
            ]
    def configure_command (self):
        return (target.AutoBuild.configure_command (self)
                + ' --with-fontconfig'
                + ' --with-freetype'
                + ' --with-jpeg'
                + ' --with-png'
                + ' --without-xpm'
                )

class Libgd__tools (tools.AutoBuild, Libgd):
    def _get_build_dependencies (self):
        return [
            'fontconfig',
            'freetype',
            'libjpeg',
            'libpng',
            'libtool',
            'zlib',
            ]
    def configure_command (self):
        return (tools.AutoBuild.configure_command (self)
                + ' --with-fontconfig'
                + ' --with-freetype'
                + ' --with-jpeg'
                + ' --with-png'
                + ' --without-xpm'
                )