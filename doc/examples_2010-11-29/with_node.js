#! /usr/local/bin/node
// by pts@fazekas.hu at Fri Nov 12 01:30:30 CET 2010

var util = require('util')

function readLine(readStream, callback) {
  if (!('buf' in readStream))
    readStream.buf = []
  function onData(data) {
    data = data.toString('UTF-8')
    readStream.buf.push(data)
    if (data.indexOf('\n') < 0)
      return
    readStream.buf = readStream.buf.join('').split('\n').reverse()
    while (readStream.buf.length > 1) {
      callback(readStream.buf.pop() + '\n')
    }
    readStream.removeListener('data', onData)
    readStream.removeListener('end', onEnd)
  }
  function onEnd() {
    readStream.removeListener('data', onData)
    readStream.removeListener('end', onEnd)
    var data = readStream.buf.join('')
    readStream.buf = null
    callback(data)
  }
  readStream.on('data', onData)
  readStream.on('end', onEnd)
}

var line_count = 0

function ticker() {
  var i = 0
  function callback() {
    i += 1
    console.log('Tick ' + i + ' with ' + line_count + ' lines.')
    setTimeout(callback, 3000)
  }
  callback()
}

function repeater() {
  var stdin = process.openStdin()
  console.log('Hi, please type and press Enter.')
  function callback(line) {
    if (line.length) {
      ++line_count
      console.log('You typed ' + util.inspect(line) + '.')
      readLine(stdin, callback)
    } else {
      console.log('End of input.')
    }
  }
  readLine(stdin, callback)
}

process.nextTick(ticker)
process.nextTick(repeater)
