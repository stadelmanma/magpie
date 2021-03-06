#!/usr/bin/env python

#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#  
#   This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.

from Crypto.Cipher import AES
from hashlib import sha256
from base64 import b64encode,b64decode
import os 
import sys
import shutil
from optparse import OptionParser
from getpass import getpass
import subprocess
import zlib
import re
import string

# Tkinter doesn't retain clipboard data after exit on unix, so we won't use it 
# there. If it has problems in windows, try using the windows api directly:
# http://stackoverflow.com/questions/579687/how-do-i-copy-a-string-to-the-clipboard-on-windows-using-python
Tkinter = None
try: 
  if sys.platform == 'win32': 
    if sys.version_info.major >= 3:
      import tkinter as Tkinter
    else:
      import Tkinter
except ImportError:
  pass

#  To Do: 
#    add an --edit option
#    add the ability to --force certain types of characters
#    add an --append option as an alternative to --import (maybe --merge?)
#    add an --update option to update a password for an entry
#    change -u option to be username entry, change -a true/false, ask for 
#      username if not specified
#    change to prompt for description if not specified.
#    confirm password when importing a database


B64_SYMBOLS = '._'
SETS = {
  "alnum": "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
  "alpha": "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
  "digit": "0123456789",
  "lower": "abcdefghijklmnopqrstuvwxyz",
  "upper": "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
}
HASH_ITERATIONS = 4096

def parseOpts( ):
  parser = OptionParser( version="%prog 0.2", 
    usage="%prog [options] [description|keywords]" )
  parser.add_option( "-a", "--add", dest="username", 
    help="Add a password to the stored passwords with the specified username." )
  parser.add_option( "-f", "--file", dest="file", 
    default=os.path.expanduser('~'+os.sep+".magpie"+os.sep+"database") , 
    help="Use FILE instead of %default for storing/retrieving passwords." )
  parser.add_option( "-g", "--generate", dest="generate", metavar="LENGTH",
    default=0, type="int",
    help="Generate a random password of the specified length instead of " + 
    "prompting for one." )
  parser.add_option( "-r", "--remove", action="store_true", dest="remove", 
    help="Remove specific password(s) from the database." )
#  parser.add_option( "-u", "--user", action="store_true", dest="get_user",
#    help="Retrieve the username instead of the password for the account." ),
  parser.add_option( "--debug", action="store_true", 
    help="Print debugging messages to stderr." )
  parser.add_option( "--list", action="store_true", dest="print_all", 
    help="Print entire database to standard output with the passwords masked." )
  parser.add_option( "--change-password", action="store_true", dest="change",
    help="Change the master password for the database." )
  parser.add_option( "--find", action="store_true", dest="find",
    help="Find an entry in the database and print its value with the " +
    "password masked." )
#  parser.add_option( "-e", "--edit", action="store_true", dest="edit",
#    help="Edit the file in the default system text editor and import the " +
#    "result as the new database." )
  parser.add_option( "-o", "--export", dest="exportFile", metavar="FILE",
    help="Export the password database to a delimited text file. Keep this " +
    "file secure, as it will contain all of your passwords in plain text. " +
    "Specify - as the filename to print to stdout." )
  parser.add_option( "-i", "--import", dest="importFile", metavar="FILE",
    help="Import a password database from a delimited text file. This will " +
    "overwrite any passwords in your current database. Specify - as the " +
    "filename to read from stdin." )
  parser.add_option( "-s", "--salt", dest="saltfile", metavar="FILE",
    default=os.path.expanduser('~'+os.sep+".magpie"+os.sep+"salt") , 
    help="Use FILE instead of %default for password salt." )
  parser.add_option( "--tr", "--sub", dest="translate", metavar="SUBS", 
    action="append",
    help="Takes an argument in the form chars:chars and translates " +
    "characters in generated passwords, replacing characters before the : " + 
    "with the corresponding character after the :." )
  parser.add_option( "-p", "--print", action="store_true", dest="print_", 
    help="Print the password to standard output instead of copying it to the " +
    "clipboard." )

  return parser.parse_args( )


def main( options, args ):
  if not options.print_:
    clipboard = Clipboard( )

  if options.generate and not options.username:
    newPass = translate( PasswordDB.generate( options.generate ), 
      options.translate )
    if options.print_:
      sys.stdout.write( newPass )
    else:
      clipboard.write( newPass )
    sys.exit( 0 )
  # prompt for password
  password = getpass( "Master Password: " )

  #Remove the old file if it exist and we are importing new data.
  if options.importFile and os.path.exists( options.file ):
    os.remove( options.file )

  try:
    pdb = PasswordDB( options.file, password, options.saltfile )
  except ValueError as e:
    sys.stderr.write( str( e ) + '\n' )
    sys.exit( -1 )

  if options.change:
    newPass       = getpass( "Enter new master password: " )
    newPassVerify = getpass( "Re-enter password: " )
    while not( newPass == newPassVerify ):
      print( "\nPasswords do not match. please try again" )
      newPass       = getpass( "Enter new master password: " )
      newPassVerify = getpass( "Re-enter password: " )
    pdb.password = newPass
    print( "Master Password Changed" )
    pdb.flush( )
    sys.exit( 0 )

  if options.print_all:
    lines = pdb.dump( ).split( '\n' )
    print( "%20s %8s %s" % PasswordDB.splitLine( lines[ 0 ] ))
    for line in lines[ 1: ]:
      print( "%20s %8s %s" % PasswordDB.splitLine( PasswordDB.mask( line )))
    sys.exit( 0 )

  if options.exportFile:
    if options.exportFile == '-':
      sys.stdout.write( pdb.dump( ) )
    else:
      exportFile = open( options.exportFile, 'w' )
      exportFile.write( pdb.dump( ))
      exportFile.close( )
    sys.exit( 0 )

  if options.importFile:
    if options.importFile == '-':
      pdb.load( sys.stdin.read( ))
    else:
      importFile = open( options.importFile )
      pdb.load( importFile.read( ))
      importFile.close( )
    pdb.flush( )
    sys.exit( 0 )

  if options.remove:
    removed = pdb.remove( *args )
    if removed:
      sys.stderr.write( "Removed the following entry:\n%s\n" % removed)
    else:
      sys.stderr.write( "Unable to locate the specified entry\n" )
    pdb.flush( )

  # BUG remove and add at the same time isn't working properly.
  if options.username:
    if options.generate:
      newPass = translate( PasswordDB.generate( options.generate ), 
        options.translate )
      if options.print_:
        sys.stdout.write( "Password: "+ newPass )
      else:
        clipboard.write( newPass )
    else:
      newPass       = getpass( "Enter password for new account: " )
      newPassVerify = getpass( "Re-enter password: " )
      while not( newPass == newPassVerify ):
        print( "\nPasswords do not match. please try again" )
        newPass       = getpass( "Enter password for new account: " )
        newPassVerify = getpass( "Re-enter password: " )
    pdb.add( options.username, newPass, str.join( ' ', args ))
    if options.generate:
      sys.stderr.write( "Generated password saved\n" )
    pdb.flush( )

  # The exit is here to allow a person to add and remove at the same time.
  # In other words, replace an entry.
  if options.remove:
    sys.exit( 0 )
  
  found = pdb.find( *args )
  if not found:
    print( "Unable to locate entry" )
    return;

  if options.find:
    found = pdb.find( *args )
    if found:
      print( "%20s %8s %s" % PasswordDB.splitLine( pdb.data.split( '\n' )[ 0 ] ))
      print( "%20s %8s %s" % PasswordDB.splitLine( PasswordDB.mask( found )))
      sys.exit( 0 )
    else:
      print( "Unable to locate entry for search terms '%s'" % 
        str.join( ' ', args ))
      sys.exit( 1 )

  else:
    entry = found.split( '\t', 2 )
  
    if options.print_:
      sys.stdout.write( entry[ 1 ] )
      sys.stdout.flush( )
      sys.stderr.write( "\n\n%s\n" % entry[ 2 ] )
      sys.stderr.write( "Username: %s\n\n" % entry[ 0 ] )
    else:
      clipboard.write( entry[ 1 ] )
      print( "" )
      print( entry[ 2 ])
      print( "Username: %s" % entry[ 0 ])


  pdb.close( )

def translate( st, replacements ):
  if not replacements:
    return st
  for repl in replacements:
    if '~' in repl:
      for i in SETS.keys( ):
        repl = repl.replace( '~%s'%i, SETS[ i ])
    _from_, to  = repl.split( ':', 1 )
    if len( _from_ ) > len( to ):
      to += to[ -1 ] * ( len( _from_ ) - len( to ))
    st = st.translate( string.maketrans( _from_, to[ :len( _from_ )]))
  return st
    
class PasswordDB( object ):
  def __init__( self, filename, password, saltfile ):
    self.filename = filename
    self.password = password
    self.saltfile = saltfile
    self.salt = self.getSalt( ) if saltfile and os.path.exists( saltfile ) \
      else None
    try:
      self.open( )
      if not ( self.data[ :29 ] == "Username\tPassword\tDescription" ):
        raise ValueError
    except ( zlib.error,ValueError ):
      raise ValueError( "You entered an incorrect password" )
      
  def flush( self ):
    if os.path.exists( self.filename ):
      shutil.copyfile( self.filename, self.filename+'~' )
    if not os.path.exists( os.path.dirname( self.filename )):
      os.makedirs( os.path.dirname( self.filename ), 0o755 )
    passFile = open( self.filename, 'w', 0o600 )
    passFile.write( b64encode( self.encode( zlib.compress( self.data[::-1], 9 ))))
    passFile.close( )
    
  def close( self ):
    self.flush( )

  def open( self ):
    if not ( os.path.exists( self.filename )):
      self.data = "Username\tPassword\tDescription\n"
      return False
    passFile = open( self.filename, 'r' )
    self.data =  zlib.decompress( self.decode( b64decode( passFile.read( ))))[::-1]
    passFile.close( )
    return True

  def dump( self ):
    return self.data
  
  def load( self, data ):
    data = data.strip( ).split( "\n" )
    self.data = ""
    for i in data:
      self.data += str.join( '\t', PasswordDB.splitLine( i.strip( )) ) + '\n'
    self.data = self.data.strip( )

  def add( self, username, password, description ):
    if not self.data[ -1 ] == '\n':
      self.data += '\n'
    self.data += str.join( '\t', ( username.strip( ), password.strip( ), 
      description.strip( ) ))
  
  def find( self, *keywords ):
    lines = self.data.split( '\n' )
    for i in xrange( 1, len( lines )):
      correctLine = True
      for j in xrange( len( keywords )):
        correctLine = correctLine and ( keywords[ j ].lower( ) in lines[ i ].lower( ) )
      if correctLine:
        return lines[ i ]
    return False
  
  def remove( self, *keywords ):
    found = self.find( *keywords )
    if not found:
      return False
    lines = self.data.split( '\n' )
    returnvalue =  lines.pop( lines.index( found ) )
    self.data = str.join( '\n', lines )
    return returnvalue

  def mask( dbentry ):
    lines = dbentry.split( '\n' )
    for i in xrange( len( lines )):
      newLine = lines[ i ].split( '\t', 2)
      newLine[ 1 ] = '(%d)' % len( newLine[ 1 ])
      lines[ i ] = str.join( '\t', newLine )
    return str.join( '\n', lines )
  mask = staticmethod( mask )

  def encode( self, text ):
    if not self.salt and not os.path.exists( self.saltfile ):
      self.salt = PasswordDB.generateSalt( 256, self.saltfile );
    key = sha256( self.password ).digest( ) + self.salt
    for i in range( HASH_ITERATIONS ):
      key = sha256( key ).digest( )
    return AES.new( key, AES.MODE_CFB, key[:16] ).encrypt( text )
  
  def decode( self, text ):
    key = sha256( self.password ).digest( )
    if ( self.salt ):
      key = key + self.salt
      for i in range( HASH_ITERATIONS ):
        key = sha256( key ).digest( )
    return AES.new( key, AES.MODE_CFB, key[:16] ).decrypt( text )

  def generate( length ):
    # get a random string containing base64 encoded data, replacing /+ with B64_SYMBOLS
    return b64encode( os.urandom( length ), B64_SYMBOLS )[ :length ]
  generate = staticmethod( generate )

  def generateSalt( length, filename=None ):
    returnvalue = os.urandom( length )
    if ( filename ):
      saltfile = open( filename, 'w' )
      saltfile.write( returnvalue )
    return returnvalue
  generateSalt = staticmethod( generateSalt )

  def getSalt( self ):
    saltreader = open( self.saltfile )
    returnvalue = saltreader.read( )
    saltreader.close( )
    return returnvalue

  def splitLine( line ):
    return tuple( re.split( "(\s*\t\s*)+", line, 2 )[::2] )
  splitLine = staticmethod( splitLine )

class Clipboard( object ):
  backend = False
  def __init__( self, backend=None ):
    object.__init__( self )
    try:
      pbcopy = bool( subprocess.Popen([ "which", "pbcopy" ], 
                     stdout=subprocess.PIPE, 
                     stderr=subprocess.PIPE ).stdout.read( ))
    except:
      pbcopy = False

    try:
      xsel = bool( subprocess.Popen([ "which", "xsel" ], 
                   stdout=subprocess.PIPE,
                   stderr=subprocess.PIPE ).stdout.read( ))
    except:
      xsel = False
    try:
      xclip = bool( subprocess.Popen([ "which", "xclip" ], 
                   stdout=subprocess.PIPE, 
                   stderr=subprocess.PIPE ).stdout.read( ))
    except:
      xclip = False

    global Tkinter
    if backend:
      self.backend = backend
    else:
      if ( Tkinter ):
        self.backend = 'tk'
      elif pbcopy:
        self.backend = 'pbcopy'
      elif xsel:
        self.backend = 'xsel'
      elif xclip:
        self.backend = 'xclip'

    if ( self.backend == 'tk' ):
      if not Tkinter:
        import Tkinter
      self._tk = Tkinter.Tk( )
      self._tk.withdraw( )

    if not self.backend: 
      sys.stderr.write( "Unable to properly initialize clipboard - " +
        "no supported backends exist\n" )
      
      # to do: check for Tk, Wx, Win32, etc.
  
  def read( self ):
    """
    Returns the contents of the clipboard
    """
    if self.backend == 'tk':
      try:
        return self._tk.clipboard_get( )
      except Tkinter.TclError:
        return str( )
    if self.backend == 'pbcopy':
      return subprocess.Popen([ 'pbpaste', '-Prefer', 'txt' ], 
        stdout=subprocess.PIPE,).stdout.read( )
    if self.backend == 'xsel':
      return subprocess.Popen([ 'xsel', '-o' ], 
        stdout=subprocess.PIPE,).stdout.read( )
    if self.backend == 'xclip':
      return subprocess.Popen([ 'xclip', '-o' ], 
        stdout=subprocess.PIPE,).stdout.read( )

  def write( self, text ):
    """
    Copies text to the system clipboard
    """
    if self.backend == 'tk': #Windows
      self._tk.clipboard_clear( )
      self._tk.clipboard_append( text, type='STRING' )
      return
    if self.backend == 'pbcopy': #OSX
      proc = subprocess.Popen([ 'pbcopy' ], 
        stdout=subprocess.PIPE, stdin=subprocess.PIPE )
      proc.stdin.write( text )
      proc.stdin.close( )
      proc.wait( )
    if self.backend == 'xsel': #Linux
      # copy to both XA_PRIMARY and XA_CLIPBOARD
      proc = subprocess.Popen([ 'xsel', '-p', '-i' ], 
        stdout=subprocess.PIPE, stdin=subprocess.PIPE )
      proc.stdin.write( text )
      proc.stdin.close( )
      proc.wait( )
      proc = subprocess.Popen([ 'xsel', '-b', '-i' ], 
        stdout=subprocess.PIPE, stdin=subprocess.PIPE )
      proc.stdin.write( text )
      proc.stdin.close( )
      proc.wait( )
      return
    if self.backend == 'xclip': #Linux
      # copy to both XA_PRIMARY and XA_CLIPBOARD
      proc = subprocess.Popen([ 'xclip', '-selection', 'primary', '-i' ],
        stdout=subprocess.PIPE, stdin=subprocess.PIPE )
      proc.stdin.write( text )
      proc.stdin.close( )
      proc.wait( )
      proc = subprocess.Popen([ 'xclip', '-selection', 'clipboard', '-i' ], 
        stdout=subprocess.PIPE, stdin=subprocess.PIPE )
      proc.stdin.write( text )
      proc.stdin.close( )
      proc.wait( )
      return

  def clear( self ):
    """
    Clear the clipboard contents
    """
    if self.backend == 'tk':
      self._tk.clipboard_clear( )
    if self.backend == 'xsel':
      subprocess.call([ 'xsel', '-pc' ])
      subprocess.call([ 'xsel', '-bc' ])
      return
    if self.backend == 'pbcopy':
      proc = subprocess.Popen([ 'pbcopy' ], stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, stdin=subprocess.PIPE )
      proc.stdin.write( '' )
      proc.stdin.close( )
      proc.wait( )
    if self.backend == 'xclip':
      proc = subprocess.Popen([ 'xclip', '-i', '-selection', 'primary' ], stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, stdin=subprocess.PIPE )
      proc.stdin.write( '' )
      proc.stdin.close( )
      proc.wait( )
      proc = subprocess.Popen([ 'xclip', '-i', '-selection', 'clipboard' ], stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, stdin=subprocess.PIPE )
      proc.stdin.write( '' )
      proc.stdin.close( )
      proc.wait( )
      return

  def close( self ):
    if self.backend == 'tk':
      self._tk.destroy( )

if __name__ == "__main__":
  main( *parseOpts( ))

