You can use syncless.console as an interactive Python interpreter (similar to `python -i`), which makes it easy to start and work with other coroutines (tasklets) in the background.

### Example invocation ###

```
"
$ python -m syncless.console
Python 2.6.5 Stackless 3.1b3 060516 (python-2.65:81084M, May 11 2010, 16:52:04) 
[GCC 4.2.4 (Ubuntu 4.2.4-1ubuntu4)] on linux2
Type "help", "copyright", "credits" or "license" for more information.
(SynclessInteractiveConsole)
>>> help                                                                        
Type help() for interactive help, or help(object) for help about object.
See more about Syncless on http://code.google.com/p/syncless/
Example commands on syncless.console:
+ticker
-ticker
wsgi.simple(8080, lambda *args: ['Hello, <b>World!</b>']) or None
>>> +ticker                                                                     
>>> ..............%
>>> -ticker
>>> wrap_tasklet(lambda: 1 / 0)()                                               
<stackless.tasklet object at 0xad76e0>
>>> 
Traceback (most recent call last):
  File "/usr/local/google/syncless/syncless/syncless/console.py", line 234, in TaskletWrapper
    function(*args, **kwargs)
  File "<console>", line 1, in <lambda>
ZeroDivisionError: integer division or modulo by zero
Exception terminated tasklet, resuming syncless.console.
>>> (Ctrl-<D>)
$ _
```

### Details ###

syncless.console is like the regular interactive Python interpreter
except that it has some useful global variables preloaded (such as
help, syncless and ticker), and it supports running coroutines
(tasklets) in the background while the user can issue Python commands.
It's an easy-to-use environment to learn Syncless and to experiment with
tasklets.

The interactive console displays a prompt. At this point all tasklets
are running and scheduled until you press the first key to type an
interactive command. While you are typing the command (after the 1st
key), other tasklets are suspended. They remain suspended until you
press _Enter_ (to finish the command or to start a multiline command).

Please note that if an uncaught exception is raised in tasklet, the
whole process exits. You can prevent that in interactive sessions by
creating your tasklets with `wrap_tasklet(Function)` instead of
`stackless.tasklet(Function)`. If you do so, the exception will be
printed, but the interactive console resumes afterwards.