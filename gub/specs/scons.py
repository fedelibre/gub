from gub import toolsbuild
from gub import mirrors

class Scons (toolsbuild.ToolsBuild):
    source = mirrors.with_template (name='scons', version='0.96.93',
                   format='gz',
                   mirror=mirrors.sf),

    def compile (self):
        pass

    def patch (self):
        pass
    
    def configure (self):
        self.system ('mkdir %(builddir)s')
    
    def install_command (self):
        return 'python %(srcdir)s/setup.py install --prefix=%(tools_prefix)s --root=%(install_root)s'

    def license_file (self):
        return '%(srcdir)s/LICENSE.txt' 
