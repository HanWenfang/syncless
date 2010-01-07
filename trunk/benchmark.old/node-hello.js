var sys = require('sys'), http = require('http');
http.createServer(function (req, res) {
  res.sendHeader(200, {'Content-Type': 'text/html'});
  res.sendBody('Hello, <i>World</i> @ 123456789!\n');
  res.finish();
}).listen(8000);
sys.puts('Server running at http://127.0.0.1:8000/');
