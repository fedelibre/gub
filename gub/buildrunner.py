"""
    Copyright (c) 2005--2007
    Jan Nieuwenhuizen <janneke@gnu.org>
    Han-Wen Nienhuys <hanwen@xs4all.nl>

    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 2, or (at your option)
    any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program; if not, write to the Free Software
    Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
"""

import datetime
import difflib
import pickle
import os
import sys
import time
#
from gub.syntax import printf
from gub import cross
from gub import build
from gub import misc
from gub import gup
from gub import loggedos
from gub import gub_log
from gub import runner
import gub.settings   # otherwise naming conflict with settings local vars.


def checksum_diff (a, b, fromfile='', tofile='',
                   fromfiledate='', tofiledate=''):
    return '\n'.join (difflib.unified_diff (a.split ('\n'),
                                            b.split ('\n'),
                                            fromfile,
                                            tofile,
                                            fromfiledate,
                                            tofiledate))

logger = gub_log.default_logger

# FIXME s/spec/build/, but we also have two definitions of package/pkg
# here: sub packages and name of global package under build

#FIXME: split spec_* into SpecBuiler?
class BuildRunner:
    def __init__ (self, manager, settings, options, specs):
        info = gub_log.default_logger.harmless
        info.write ('MANAGER: ' + settings.platform + '\n')
        self.managers = {settings.platform : manager }
        self.settings = settings
        self.options = options
        self.specs = specs

        # spec name -> string
        self.checksums = dict ()
        self.failed_checksums = dict ()

        # PATH = os.environ['PATH']
        # cross_prefix is also necessary for building cross packages, such as GCC
        # yes, so we set that in cross.AutoBuild.get_substitution_dict ()
        # we cannot do it here, as this will break all tools::* checksums
        # going from mingw::libtool to darwin-x86::libtool
        # os.environ['PATH'] = self.settings.expand ('%(cross_prefix)s/bin:' + PATH, locals ())
        self.add_packages_to_manager (self.specs)

    def manager (self, platform):
        if platform not in self.managers:
            info = gub_log.default_logger.harmless
            info.write ('MANAGER for platform: ' + platform + '\n')
            settings = gub.settings.Settings (platform)
            self.managers[platform] = gup.DependencyManager (settings.system_root)
        return self.managers[platform]
        
    def add_packages_to_manager (self, package_object_dict):
        ## Ugh, this sucks: we now have to have all packages
        ## registered at the same time.
        for spec in list (package_object_dict.values ()):
            for package in spec.get_packages ():
                self.manager (package.platform ()).register_package_dict (package.dict ())

    def calculate_checksums (self):
        gub_log.verbose ('calculating checksums\n')
        for spec in list (self.specs.values ()):
            name = spec.platform_name ()
            logger = gub_log.NullCommandLogger ()

            command_runner = runner.DeferredRunner (logger)
            spec.connect_command_runner (command_runner)
            spec.build (skip=['download'])
            spec.connect_command_runner (None)

            self.checksums[name] = command_runner.checksum ()
            reason = self.spec_checksums_fail_reason (spec)
            if reason:
                self.failed_checksums[name] = reason

    # FIXME: move to gup.py or to build.py?
    def spec_checksums_fail_reason (self, spec):
        # need to read package header to read checksum_file.  since
        # checksum is per buildspec, only need to inspect one package.
        pkg = spec.get_packages ()[0]    
        name = pkg.name ()
        pkg_dict = self.manager (pkg.platform ()).package_dict (name)

        checksum_file = pkg_dict['checksum_file']
        try:
            build_checksum_ondisk = open (pkg_dict['checksum_file']).read ()
            checksum_time = time.ctime (os.stat (checksum_file).st_mtime)
        except IOError:
            build_checksum_ondisk = '0000'
            checksum_time = '0000'

        # fixme: spec.build_checksum () should be method.
        reason = ''
        hdr = pkg.expand ('%(split_hdr)s')
        if spec.install_after_build:
            if spec.source_checksum () != pkg_dict['source_checksum']:
                reason = 'source %s -> %s (memory)' % (spec.source_checksum (), pkg_dict['source_checksum'])

        if reason == '' and self.checksums[spec.platform_name ()] != build_checksum_ondisk:
            failure = 'diff'
            spec_name = spec.name ()
            spec_platform = spec.platform ()
            diff = checksum_diff (build_checksum_ondisk,
                                  self.checksums[spec.platform_name ()],
                                  checksum_file,
                                  'THIS BUILD',
                                  checksum_time,
                                  time.ctime (time.time ()))
            message = '\n' + diff
            reason = '\n *** Checksum mismatch: %(failure)s (%(spec_name)s, %(spec_platform)s)%(message)s\n' % locals ()

        if spec.install_after_build:
            if not reason and not os.path.exists (hdr):
                reason = 'no such file: header: %(hdr)s' % locals ()
            elif not reason:
                hdr_dict = dict (pickle.load (open (hdr, 'rb')))
                if spec.source_checksum () != hdr_dict['source_checksum']:
                    reason = 'source %s -> %s (disk)' % (spec.source_checksum (), hdr_dict['source_checksum'])

        # we don't use cross package checksums, otherwise we have to
        # rebuild everything for every cross package change.
        return reason

    # FIXME: this should be in gpkg/gup.py otherwise it's impossible
    # to install packages in a conflict situation manually
    def spec_conflict_resolution (self, spec, pkg):
        pkg_name = pkg.name ()
        install_candidate = pkg
        subname = ''
        if spec.name () != pkg_name:
            subname = pkg_name.split ('-')[-1]
        manager = self.manager (spec.platform ())
        if subname in spec.get_conflict_dict ():
            for c in spec.get_conflict_dict ()[subname]:
                if manager.is_installed (c):
                    printf ('  %(c)s conflicts with %(pkg_name)s' % locals ())
                    conflict_source = manager.source_name (c)
                    # FIXME: implicit provides: foo-* provides foo-core,
                    # should implement explicit provides
                    if conflict_source + '-core' == pkg_name:
                        printf ('    non-core %(conflict_source)s already installed'
                               % locals ())
                        printf ('      skipping request to install %(pkg_name)s'
                               % locals ())
                        install_candidate = None
                        continue
                    printf ('    removing %(c)s' % locals ())
                    manager.uninstall_package (c)
        return install_candidate

    def pkg_install (self, spec, pkg):
        manager = self.manager (spec.platform ())
        if not manager.is_installed (pkg.name ()):
            install_candidate = self.spec_conflict_resolution (spec, pkg)
            if install_candidate:
                manager.unregister_package_dict (install_candidate.name ())
                manager.register_package_dict (install_candidate.dict ())
                manager.install_package (install_candidate.name ())

    def spec_install (self, spec):
        for pkg in spec.get_packages ():
            self.pkg_install (spec, pkg)

    def get_skip_stages (self):
        """Returns list of stages (strings) to be skipped.

        Uses command line options as input.
        """
        skip = []
        if self.options.offline:
            skip += ['download']
        if not self.options.build_source:
            skip += ['src_package']
        if self.options.keep_build:
            skip += ['clean']
        return skip
    
    def spec_is_installable (self, spec):
        return misc.forall (self.manager (p.platform ()).is_installable (p.name ())
                            for p in spec.get_packages ())

    def spec_all_installed (self, spec):
        all_installed = True
        for p in spec.get_packages ():
            all_installed = (all_installed
                             and self.manager (p.platform ()).is_installed (p.name ()))
        return all_installed

    def spec_build (self, spec_name):
        spec = self.specs[spec_name]
        if self.spec_all_installed (spec):
            return
        checksum_fail_reason = self.failed_checksums.get (spec_name, '')
        if ((not checksum_fail_reason or self.options.lax_checksums)
            and not spec.install_after_build):
            return
        global logger
        if self.options.log == 'build':
            # This is expecially broken with multi-platform builds...
            logger = gub_log.default_logger
        else:
            if self.options.log == 'platform':
                log = os.path.join (spec.settings.logdir, 'build.log')
            else:
                log = os.path.join (spec.settings.logdir,
                                    misc.strip_platform (spec_name)) + '.log'
            if os.path.isfile (log):
                misc.rename_append_time (log)
            logger = gub_log.CommandLogger (log, gub_log.default_logger.threshold)
        if checksum_fail_reason:
            rebuild = 'must'
            if self.options.lax_checksums:
                rebuild = 'should'
            logger.write_log ('%(rebuild)s rebuild: %(spec_name)s\n' % locals (), 'verbose')
        else:
            logger.write_log ('checksum ok: %(spec_name)s\n' % locals (), 'verbose')

        if gub_log.get_numeric_loglevel ('verbose') > logger.threshold:
            logger.write_log ('\n'.join (checksum_fail_reason.split ('\n')[:10]), 'verbose')
        logger.write_log (checksum_fail_reason, 'output')

        if ((checksum_fail_reason and not self.options.lax_checksums)
            or not self.spec_is_installable (spec)):
            deferred_runner = runner.DeferredRunner (logger)
            spec.connect_command_runner (deferred_runner)
            spec.runner.stage ('building package: %s\n' % spec_name)
            skip = self.get_skip_stages () ### + spec.get_done ()
            skip = [x for x in skip if x != self.options.stage]
            
            spec.build (self.options, skip)
            spec.connect_command_runner (None)
            deferred_runner.execute_deferred_commands ()
            checksum_file = spec.expand ('%(checksum_file)s')
            if checksum_file:
                if len (self.checksums[spec_name].split ('\n')) < 5:
                    # Sanity check.  This can't be right.  Do not
                    # overwrite precious [possibly correct] checksum.
                    raise Exception ('BROKEN CHECKSUM:' + self.checksums[spec_name])
                if os.path.isfile (checksum_file):
                    misc.rename_append_time (checksum_file)
                open (checksum_file, 'w').write (self.checksums[spec_name])
            loggedos.system (gub_log.default_logger, spec.expand ('rm -f %(stamp_file)s'))
        # Ugh, pkg_install should be stage
        if spec.install_after_build and not self.spec_all_installed (spec):
            logger.write_log (spec.stage_message ('pkg_install'), 'stage')
            self.spec_install (spec)
        gub_log.default_logger.write_log ('\n', 'stage')

    def is_installed_spec (self, spec_name):
        spec = self.specs[spec_name]
        for pkg in spec.get_packages ():
            if self.manager (pkg.platform ()).is_installed (pkg.name ()):
                return True
        return False

    def is_outdated_spec (self, spec_name):
        spec = self.specs[spec_name]
        checksum_fail_reason = self.failed_checksums.get (spec_name, '')
        checksum_ok = '' == checksum_fail_reason
        for pkg in spec.get_packages ():
            if (not self.manager (pkg.platform ()).is_installable (pkg.name ())
                or not checksum_ok):
                return True
        return False

    def uninstall_spec (self, spec):
        for pkg in spec.get_packages ():
            if (self.manager (pkg.platform ()).is_installed (pkg.name ())):
                self.manager (pkg.platform ()).uninstall_package (pkg.name ())

    def outdated_names (self, deps):
        return [name for name in deps
                if (self.is_outdated_spec (name)
                    and not (self.options.lax_checksums
                             and self.spec_is_installable (self.specs[name])))]

    def uninstall_specs (self, lst):
        for name in lst:
            self.uninstall_spec (self.specs[name])

    def build_source_packages (self, names):
        deps = [d for d in names if d in self.specs]
        platform = self.settings.platform
        outdated = self.outdated_names (deps)
        # fail_str: keep ordering of names
        fail_str = (' '.join ([s for s in deps if s in outdated ])
                    .replace (misc.with_platform ('', platform), ''))
        if not fail_str:
            fail_str = '<nothing to be done>.'
        gub_log.default_logger.write_log ('must rebuild[%(platform)s]: %(fail_str)s\n' % locals (), 'stage')
        if self.options.dry_run:
            sys.exit (0)
        outdated_installed = [x for x in list (reversed (outdated))
                              if self.is_installed_spec (x)]
        if outdated_installed:
            platform = self.settings.platform
            outdated_str = (' '.join (outdated_installed)
                            .replace (misc.with_platform ('', platform), ''))
            gub_log.default_logger.write_log ('removing outdated[%(platform)s]: %(outdated_str)s\n' % locals (), 'stage')
            self.uninstall_specs (outdated_installed)
        global target
        for spec_name in deps:
            target = spec_name
            self.spec_build (spec_name)
            logger = gub_log.default_logger
        target = None

target = None

def main ():
    boe

if __name__ == '__main__':
    main ()
