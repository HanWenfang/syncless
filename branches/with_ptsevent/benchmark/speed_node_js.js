// #! /usr/local/bin/node
// by pts@fazekas.hu at Thu Jan  7 17:45:50 CET 2010

function lprngNext(seed) {
  var n = (((1664525 * seed) & 0xffffffff) + 1013904223) & 0xffffffff
  return n < 0 ? n + 4294967296 : n;
}

var sys = require('sys'), http = require('http')
http.createServer(function (req, res) {
  // SUXX: cannot get client IP address.
  sys.puts('info: new request arrived')
  res.sendHeader(200, {'Content-Type': 'text/html'})
  if (req.uri.path == '/') {
    res.sendBody('<a href="/0">start at 0</a><p>Hello, World!\n')
  } else {
    var next_num = lprngNext(parseInt(req.uri.path.substr(1)))
    res.sendBody(['<a href="/', next_num, '">continue with ',
                  next_num, '</a>\n'].join(''))
  }
  res.finish()
}).listen(8080)
sys.puts('info: server running at http://127.0.0.1:8080/')
