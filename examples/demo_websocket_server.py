#! /usr/local/bin/stackless2.6
# by pts@fazekas.hu at Sun Aug 29 20:13:50 CEST 2010

"""Demo WebSocket server using syncless.wsgi.

You need a recent browser to test this demo with:

* Chrome 4.0.249+, 5.0, 6.0 etc.
* Firefox 4.0+ (doesn't work in 3.6)
* Safari 5.x etc. (doesn't work in 4.x)
* doesn't work in Opera 9.x, 10.x
* doesn't work in Internet Explorer (5.x, 6.x, 7.x, 8.x, 9.x)

web-socket-js might be added in a future, which will add Firefox 3.0, Safari
4.x, Opera and Internet Explorer support.

See also the Syncless FAQ entry about WebSocket.

See more links and demos at:

  http://stackoverflow.com/questions/1253683/websocket-for-html5
"""

__author__ = 'pts@fazekas.hu (Peter Szabo)'

import logging
import os
import sys
from syncless import wsgi


def WsgiApp(env, start_response):
  # This is only needed by the web-socket-js emulation (which we don't use
  # by default).
  # TODO(pts): Add support for web-socket-js emulation.
  if env['PATH_INFO'] == 'policy-file':
    return wsgi.SendWildcardPolicyFile(env, start_response)

  if env.get('HTTP_UPGRADE') == 'WebSocket':
    start_response('101', [('Upgrade', 'WebSocket')])
    read_msg = env['syncless.websocket_read_msg']
    write_msg = env['syncless.websocket_write_msg']
    write_msg('Hello!')
    for msg in iter(read_msg, None):
      if isinstance(msg, str):
        # Make sure whe have a Unicode string (list of code points), so we can
        # safely reverse it below.
        msg = msg.decode('UTF-8')
      write_msg(msg[::-1])  # Send back reversed.
    return ()

  if env['PATH_INFO'] == '/':
    start_response('200 OK', [('Content-Type', 'text/html; charset=UTF-8')])
    # For web-socket-js:
    #   <!-- Include these three JS files: -->
    #   <script type="text/javascript" src="swfobject.js"></script>
    #   <script type="text/javascript" src="FABridge.js"></script>
    #   <script type="text/javascript" src="web_socket.js"></script>
    #   // Set URL of your WebSocketMain.swf here:
    #   WEB_SOCKET_SWF_LOCATION = "WebSocketMain.swf";
    #   // Set this to dump debug message from Flash to console.log:
    #   WEB_SOCKET_DEBUG = true;
    # TODO(pts): Investigate how ws.onerror can be called.
    return (r"""<html><head>
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
  <title>Sample WebSocket client</title>
  <script type="text/javascript">
    var ws, outputCount = 0
    function init() {
      output("init")
      document.getElementById("input").focus()
      ws = new WebSocket("ws://" + document.location.host + "/")
      output("ws-created")
      ws.onopen = function() { output("onopen") }
      ws.onmessage = function(e) { output("onmessage: " + e.data) }
      ws.onclose = function() { output("onclose") }
      ws.onerror = function() { output("onerror") }
    }
    function onSubmit() {
      var input = document.getElementById("input")
      ws.send(input.value)
      output("send: " + input.value)
      input.value = ""
      input.focus()
    }
    function onCloseClick() {
      ws.close();
    }
    function output(str) {
      var log = document.getElementById('log')
      var text = document.createTextNode(++outputCount + '. ' + str)
      var br = document.createElement('br')
      log.insertBefore(br, log.childNodes[0])
      log.insertBefore(text, log.childNodes[0])
    }
  </script>
</head><body onload="init()">
  <form onsubmit="onSubmit(); return false">
    <input type="text" id="input">
    <input type="submit" value="Send">
    <button onclick="onCloseClick(); return false">close</button>
  </form>
  <div id="log"></div>
</body></html>""",)

  start_response('404 Not Found', [('Content-Type', 'text/plain')])
  return 'not found: %s' % env['PATH_INFO']


if __name__ == '__main__':
  logging.BASIC_FORMAT = '[%(created)f] %(levelname)s %(message)s'
  logging.root.setLevel(logging.DEBUG)
  wsgi.RunHttpServer(WsgiApp)
