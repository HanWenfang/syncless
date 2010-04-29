#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Tue Feb  9 18:42:57 CET 2010

"""Python distutils setup.py build script for Syncless.

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
"""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import glob
import os
import os.path
import sys
import stat
from distutils import log
from distutils.ccompiler import CCompiler
from distutils.ccompiler import new_compiler
from distutils.command.build import build
from distutils.core import Command
from distutils.core import Extension
from distutils.core import setup
from distutils.dir_util import mkpath
from distutils.dist import Distribution
from distutils.errors import CompileError
from distutils.errors import LinkError
from distutils.unixccompiler import UnixCCompiler

UnixCCompiler.nosyncless_find_library_file = UnixCCompiler.find_library_file

def FindLibraryFile(self, dirs, lib, *args, **kwargs):
  if len(dirs) == 1 and os.path.isfile(os.path.join(dirs[0], lib)):
    # e.g. '/usr/local/lib/libfoo.so.5'
    return os.path.join(dirs[0], lib)
  return self.nosyncless_find_library_file(dirs, lib, *args, **kwargs)

UnixCCompiler.find_library_file = classmethod(FindLibraryFile)

class MyBuild(build):
  def has_sources(self):
    return self.has_pure_modules or self.has_ext_modules

  sub_commands = [
      ('build_ext_dirs', build.has_ext_modules),
      ] + build.sub_commands + [
      ('build_ext_symlinks', build.has_ext_modules),
      ('build_src_symlinks', has_sources)]

#print MyBuild.sub_commands

class MyBuildExtDirs(Command):
  """Create symlinks to .so files.
  
  Create symlinks so scripts in the source dir can be run with PYTHONPATH=.
  without install.
  """

  def run(self):
    for ext in self.distribution.ext_modules:
      #assert ext.include_dirs == []
      if callable(ext.library_dirs):
        update_dict = ext.library_dirs(self)
        assert isinstance(update_dict, dict)
        ext.library_dirs = []
        ext.include_dirs = []
        for key in sorted(update_dict):
          value = update_dict[key]
          assert isinstance(value, list) or isinstance(value, tuple)
          assert hasattr(ext, key), key
          assert isinstance(getattr(ext, key), list)
          # ext.library_dirs.extend(update_dict['library_dirs'])
          getattr(ext, key).extend(value)

  def initialize_options(self):
    pass

  def finalize_options(self):
    pass


class MyBuildExtSymlinks(Command):
  """Create symlinks to .so files.
  
  Create symlinks so scripts in the source dir can be run with PYTHONPATH=.
  without install.
  """

  def run(self):
    # '.so'
    build_ext_cmd = self.get_finalized_command('build_ext')
    so_ext = build_ext_cmd.compiler.shared_lib_extension
    for ext in self.distribution.ext_modules:
      name_items = ext.name.split('.')
      if len(name_items) == 2 and os.path.isdir(name_items[0]):
        # build_ext_cmd.build_lib: 'build/lib.linux-i686-2.6'
        # '.'.join(name_items) == 'syncless/coio'
        so_file = os.path.join(build_ext_cmd.build_lib,
                               name_items[0], name_items[1] + so_ext)
        link_from = os.path.join(name_items[0], name_items[1] + so_ext)
        link_to = os.path.join('..', so_file)
        symlink(link_to, link_from)

  def initialize_options(self):
    pass

  def finalize_options(self):
    pass


class MyBuildSrcSymlinks(Command):
  """Create symlinks to package source directories.
  
  Create symlinks so, if combined with MyBuildExtSymlinks, scripts in the
  source dir can be run even without PYTHONPATH=. without install.
  """

  def run(self):
    src_dirs = self.distribution.symlink_script_src_dirs
    if src_dirs:
      for package in self.distribution.packages:  # package = 'syncless'
        package = package.replace('/', '.')
        if '.' not in package:
          for src_dir in src_dirs:  # src_dir = 'test'
            link_from = os.path.join(src_dir, package)
            link_to = os.path.join('..', package)
            symlink(link_to, link_from)

  def initialize_options(self):
    pass

  def finalize_options(self):
    pass

# Make self.distribution.symlink_script_src_dirs visible.
Distribution.symlink_script_src_dirs = None

def symlink(link_to, link_from):
  log.info('symlinking %s -> %s' % (link_from, link_to))
  try:
    st = os.lstat(link_from)
    if stat.S_ISLNK(st.st_mode):
      os.remove(link_from)  # Remove old symlink.
  except OSError:
    pass
  os.symlink(link_to, link_from)


def GetCompiler(command_obj):
  build_ext_cmd = command_obj.get_finalized_command('build_ext')
  if build_ext_cmd.dry_run:
    return retval  # TODO(pts): Do better.
  if isinstance(build_ext_cmd.compiler, CCompiler):
    return build_ext_cmd.compier
  else:
    return new_compiler(compiler=build_ext_cmd.compiler,
                        verbose=build_ext_cmd.verbose,
                        dry_run=build_ext_cmd.dry_run,
                        force=build_ext_cmd.force)


def HasSymbols(compiler, symbols=(),
               includes=None,
               include_dirs=None,
               libraries=None,
               library_dirs=None):
  """Return a boolean indicating whether all symbols are defined on
  the current platform.  The optional arguments can be used to
  augment the compilation environment.
  
  Different from CCompiler.has_function:

  * ignores function arguments, just tries to convert to (void*).
  * multiple symbols (conjunction)
  * symbols should not be macros (so library linking can be tested)
  * runs the linked executable with /bin/sh
  """
  if not symbols:
    return True

  import tempfile
  if includes is None:
    includes = []
  if include_dirs is None:
    include_dirs = []
  if libraries is None:
    libraries = []
  if library_dirs is None:
    library_dirs = []
  mkpath('tmp')
  fname = 'tmp/check_c_sym_' + symbols[0] + '.c'
  f = open(fname, "w")
  if () in includes:
    assert len(includes) == 1
    for symbol in symbols:
      f.write("extern void %s(void);\n" % symbol)
  else:
    for incl in includes:
      f.write("""#include "%s"\n""" % incl)
  f.write("int main(int argc, char **argv) {\n")
  f.write("  int c = %d;\n" % len(symbols))
  for symbol in symbols:
    f.write("  if ((void*)(%s) != (void*)main) --c;\n" % symbol)
  f.write("  return c;\n");
  f.write("}\n")
  f.close()
  try:
    # Strips leading '/' from fname.
    objects = compiler.compile([fname], include_dirs=include_dirs)
  except CompileError:
    return False

  execfn = os.path.splitext(fname)[0] + '.out'
  try:
    compiler.link_executable(objects, execfn,
                             libraries=libraries,
                             library_dirs=library_dirs)
  except (LinkError, TypeError):
    return False
  assert '/' in execfn
  assert '\0' not in execfn
  if 0 != os.system("exec '%s'" % execfn.replace("'", "'\\''")):
    log.error('running %s failed' % execfn)
    return False
  return True


def FindLib(retval, compiler, prefixes, includes, library, symbols,
            link_with_prev_libraries=None):
  for prefix in prefixes:
    if (prefix and
        (() in includes or includes ==
         [idir for idir in includes if
          os.path.isfile(prefix + '/include/' + idir)]) and
        ('/' in library or 
         glob.glob(prefix + '/lib/lib' + library + '.*'))):
      include_dir = '%s/include' % prefix
      library_dir = '%s/lib' % prefix
      libraries = [library]
      if link_with_prev_libraries:
        # library_dirs same order as in final retval.
        library_dirs = list(retval['library_dirs'])
        libraries.extend(link_with_prev_libraries)
      else:
        library_dirs = []
      if library_dir != os.path.dirname(library):
        library_dirs.append(library_dir)
      if HasSymbols(compiler=compiler, symbols=symbols,
                    includes=includes, include_dirs=[include_dir],
                    libraries=libraries, library_dirs=[library_dir]):
        if '/' in library:
          log.info('found %s as %s' % (os.path.basename(library), library))
        else:
          log.info('found lib%s in %s' % (library, prefix))
        if include_dir not in retval['include_dirs']:
          retval['include_dirs'].append(include_dir)
        if (library_dir != os.path.dirname(library) and
            library_dir not in retval['library_dirs']):
          retval['library_dirs'].append(library_dir)
        retval['is_found'] = True
        return True
  log.error('library %s not found or not working' % library)
  return False

def FindLibEv(command_obj):
  # We could add more directories (e.g. those in /etc/ld.so.conf), but that's
  # system-specific, see http://stackoverflow.com/questions/2230467 .
  # TODO(pts): Issue a fatal error if libev or libevhdns was not found.
  # TODO(pts): Find libevhdns separately.
  retval = {'include_dirs': [], 'library_dirs': [], 'libraries': [],
            'define_macros': [], 'is_found': False}
  compiler = GetCompiler(command_obj)
  prefixes = os.getenv('LD_LIBRARY_PATH', '').split(':') + [
                sys.prefix, '/usr']
  is_found = False

  is_asked = False
  event_driver = None
  if os.getenv('SYNCLESS_USE_LIBEV', ''):
    assert event_driver is None
    event_driver = 'libev'
  if os.getenv('SYNCLESS_USE_LIBEVENT1', ''):
    assert event_driver is None
    event_driver = 'libevent1'
  if os.getenv('SYNCLESS_USE_LIBEVENT2', ''):
    assert event_driver is None
    event_driver = 'libevent2'

  if event_driver in (None, 'libev'):
    if (FindLib(retval=retval, compiler=compiler, prefixes=prefixes,
            includes=['ev.h'], library='ev', symbols=['ev_once']) and
        FindLib(retval=retval, compiler=compiler, prefixes=prefixes,
            includes=[()], library='evhdns', symbols=['evdns_resolve_ipv4'],
            link_with_prev_libraries=['ev'])):
      event_driver = 'libev'
      retval['is_found'] = True
      retval['libraries'].extend(['evhdns', 'ev'])
      retval['define_macros'].append(('COIO_USE_LIBEV', None))

  if event_driver in (None, 'libevent2'):
    if (FindLib(retval=retval, compiler=compiler, prefixes=prefixes,
            includes=['event2/event_compat.h'], library='event',
            symbols=['event_init', 'event_loop']) and
        FindLib(retval=retval, compiler=compiler, prefixes=prefixes,
            includes=['event2/dns.h', 'event2/dns_compat.h'],
            library='event',
            symbols=['evdns_resolve_ipv4', 'evdns_resolve_reverse_ipv6'])):
      event_driver = 'libevent2'
      retval['is_found'] = True
      # TODO(pts): Try to link something libevent1 doesn't have.
      retval['libraries'].extend(['event'])
      retval['define_macros'].append(('COIO_USE_LIBEVENT2', None))

  if event_driver in (None, 'libevent1'):
    lib_event = 'event'
    prefixes2 = list(prefixes)
    for prefix in prefixes:
      # Prefer libevent-1.4.so* because libevent.so might be libevent2 (sigh).
      lib_file = os.path.join(prefix, 'lib', 'libevent-1.4.so.2')
      if os.path.isfile(lib_file):
        lib_event = lib_file
        prefixes = [prefix]
        break
    if (FindLib(retval=retval, compiler=compiler, prefixes=prefixes2,
            includes=['event.h'], library=lib_event,
            symbols=['event_init', 'event_loop']) and
        FindLib(retval=retval, compiler=compiler, prefixes=prefixes2,
            includes=['evdns.h'], library=lib_event,
            symbols=['evdns_resolve_ipv4', 'evdns_resolve_reverse_ipv6'])):
      event_driver = 'libevent1'
      retval['is_found'] = True
      retval['libraries'].append(lib_event)
      retval['define_macros'].append(('COIO_USE_LIBEVENT1', None))

  if not retval.pop('is_found'):
    raise LinkError('libevent/libev not found')

  repr_retval = repr(retval)
  log.info('using C env %s' % repr_retval)
  try:
    old_repr_retval = open('setup.cenv').read()
  except FileError:
    old_repr_retval = None
  if repr_retval != old_repr_retval:
    open('setup.cenv', 'w').write(repr_retval)
  return retval


event = Extension(name='syncless.coio',
                  sources=['coio_src/coio.c'],
                  depends=['coio_src/coio_c_helper.h',
                           'coio_src/coio_c_evbuffer.h',
                           'coio_src/coio_ev_event.h',
                           'setup.cenv',
                          ],
                  # Using a function for library_dirs here is a nonstandard
                  # distutils extension, see also MyBuildExtDirs.
                  library_dirs=FindLibEv,
                  libraries=[])

# chdir to to the directory containing setup.py. Building extensions wouldn't
# work otherwise.
os.chdir(os.path.join('.', os.path.dirname(__file__)))
if __file__[0] != '/':
    __file__ = os.path.basename(__file__)

version = {}
f = open(os.path.join('syncless', 'version.py'))
exec f in version
assert isinstance(version.get('VERSION'), str)

setup(name='syncless',
      version=version['VERSION'],
      description='Syncless: asynchronous client and server library using Stackless Python',
      author='Peter Szabo',
      author_email='pts@fazekas.hu',
      maintainer='Peter Szabo',
      maintainer_email='pts@fazekas.hu',
      url='http://code.google.com/p/syncless/',
      download_url='http://syncless.googlecode.com/files/syncless-%s.tar.gz' %
                   version['VERSION'],
      packages=['syncless'],
      long_description=
          "Syncless is an experimental, lightweight, non-blocking (asynchronous) client "
          "and server socket network communication library for Stackless Python 2.6. "
          "For high speed, Syncless uses libev (similar to libevent), and parts of "
          "Syncless' code is implemented in C (Pyrex). Thus Syncless can be faster than "
          "many other non-blocking Python communication libraries. Syncless contains an "
          "asynchronous DNS resolver (using evdns) and a HTTP server capable of serving "
          "WSGI applications. Syncless aims to be a coroutine-based alternative of "
          "event-driven networking engines (such as Twisted and FriendFeed's Tornado), "
          "and it's a competitor of gevent, pyevent, python-libevent, Eventlet and "
          "Concurrence.",
      license="GPL v2",
      platforms=["Unix"],
      classifiers=[
          "Development Status :: 3 - Alpha",
          "Environment :: Console",
          "Environment :: No Input/Output (Daemon)",
          "Environment :: Other Environment",
          "Intended Audience :: Developers",
          "License :: OSI Approved :: GNU General Public License (GPL)",
          "Operating System :: POSIX :: Linux",
          "Operating System :: Unix",
          "Programming Language :: Python :: 2.6",
          "Topic :: Internet",
          "Topic :: Internet :: WWW/HTTP :: Dynamic Content :: CGI Tools/Libraries",
          "Topic :: Internet :: WWW/HTTP :: HTTP Servers",
          "Topic :: Internet :: WWW/HTTP :: WSGI :: Application",
          "Topic :: Internet :: WWW/HTTP :: WSGI :: Server",
          "Topic :: Software Development :: Libraries :: Application Frameworks",
          "Topic :: Software Development :: Libraries :: Python Modules",
      ],
      requires=['stackless'],
      ext_modules = [ event ],
      cmdclass = {'build': MyBuild,
                  'build_ext_dirs': MyBuildExtDirs,
                  'build_ext_symlinks': MyBuildExtSymlinks,
                  'build_src_symlinks': MyBuildSrcSymlinks,
                 },
      symlink_script_src_dirs=['test', 'benchmark', 'coio_src', 'examples'],
     )
