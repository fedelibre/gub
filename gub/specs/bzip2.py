from gub import tools
from gub import target

class Bzip2 (target.MakeBuild):
    source = 'https://web.archive.org/web/20170824030156/http://www.bzip.org/1.0.5/bzip2-1.0.5.tar.gz'
    compile_flags = ''' -f Makefile-libbz2_so CC='%(toolchain_prefix)sgcc %(target_gcc_flags)s -fno-stack-protector' '''
    install_flags = (target.MakeBuild.install_flags
                     + ' PREFIX=%(install_prefix)s')
    def install (self):
        target.MakeBuild.install (self)
        self.system ('cp -pv %(builddir)s/libbz2.so* %(install_prefix)s/lib')
        # junk broken symlinks
        self.system ('cd %(install_prefix)s/bin && rm -f bzless bzfgrep bzegrep bzcmp')

class Bzip2__tools (tools.MakeBuild):
    source = 'https://web.archive.org/web/20170824030156/http://www.bzip.org/1.0.5/bzip2-1.0.5.tar.gz'
    compile_flags = ' -f Makefile-libbz2_so'
    install_flags = (tools.MakeBuild.install_flags
                     + ' PREFIX=%(install_prefix)s')
    def install (self):
        tools.MakeBuild.install (self)
        self.system ('cp -pv %(builddir)s/libbz2.so* %(install_prefix)s/lib')
        # junk broken symlinks
        self.system ('cd %(install_prefix)s/bin && rm -f bzless bzfgrep bzegrep bzcmp')
