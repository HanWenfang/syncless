/* by pts@fazekas.hu at Fri May  7 14:40:23 CEST 2010 */

#ifdef COIO_USE_CO_STACKLESS
#include "frameobject.h"  /* Needed by core/stackless_structs.h */
#include "core/stackless_structs.h"
#include "stackless_api.h"
PyAPI_FUNC(int) PyTasklet_GetBlocked(PyTaskletObject *tasklet_obj);
#endif

#ifdef COIO_USE_CO_GREENLET
/* by pts@fazekas.hu at Thu May  6 20:09:26 CEST 2010 */

typedef struct _bomb {
  PyObject_HEAD
  PyObject *bomb_type;
  PyObject *bomb_value;
  PyObject *bomb_traceback;
  PyObject *bomb_weakreflist;
} PyBombObject;

typedef struct _tasklet {
  PyObject_HEAD
  struct _tasklet *next;
  struct _tasklet *prev;
  /* void *xframe; real stackless_structs.h has this here */
  PyObject *tempval;
  PyObject *tasklet_weakreflist;
} PyTaskletObject;

static PyObject *bomb_new(PyTypeObject *type,
                          PyObject *args,
                          PyObject *kwargs) {
  PyBombObject *bomb;
  if (NULL != (bomb = (PyBombObject*)type->tp_alloc(type, 0))) {
    bomb->bomb_weakreflist = NULL;
    bomb->bomb_type = NULL;
    bomb->bomb_value = NULL;
    bomb->bomb_traceback = NULL;
    /* We ignore args and kwargs here, and set them in bomb_init, so
     * subclasses can call __init__.
     */
    (void)args;
    (void)kwargs;
  }
  return (PyObject*)bomb;
}

static int bomb_init(PyBombObject *bomb,
                     PyObject *args,
                     PyObject *kwargs) {
  static char *kwlist[] = {"type", "value", "traceback", NULL};
  PyObject *bomb_type = Py_None, *bomb_value = Py_None;
  PyObject *bomb_traceback = Py_None, *tmp;
  bomb->bomb_weakreflist = NULL;
  bomb->bomb_type = NULL;
  bomb->bomb_value = NULL;
  bomb->bomb_traceback = NULL;
  /* We ignore args and kwargs here, and set them in bomb_init, so
   * subclasses can call __init__.
   */
  if (PyTuple_GET_SIZE(args) == 1 &&
      PyTuple_Check(PyTuple_GET_ITEM(args, 0)))
    args = PyTuple_GET_ITEM(args, 0);
  if (!PyArg_ParseTupleAndKeywords(args, kwargs, "|OOO:bomb", kwlist,
                                   &bomb_type,
                                   &bomb_value,
                                   &bomb_traceback)) {
    Py_DECREF(bomb);
    return -1;
  }
  tmp = bomb->bomb_type;
  Py_INCREF(bomb_type);
  bomb->bomb_type = bomb_type;
  Py_XDECREF(tmp);
  tmp = bomb->bomb_value;
  Py_INCREF(bomb_value);
  bomb->bomb_value = bomb_value;
  Py_XDECREF(tmp);
  tmp = bomb->bomb_traceback;
  Py_INCREF(bomb_traceback);
  bomb->bomb_traceback = bomb_traceback;
  Py_XDECREF(tmp);
  return 0;
}

static int bomb_traverse(PyBombObject *bomb, visitproc visit, void *arg) {
  Py_VISIT(bomb->bomb_type);
  Py_VISIT(bomb->bomb_value);
  Py_VISIT(bomb->bomb_traceback);
  return 0;
}

static void bomb_clear(PyBombObject *bomb) {
  Py_CLEAR(bomb->bomb_type);
  Py_CLEAR(bomb->bomb_value);
  Py_CLEAR(bomb->bomb_traceback);
}

static void bomb_dealloc(PyBombObject *bomb) {
  /* TODO(pts): use GC, as in scheduling.c: PyObject_GC_Track(bomb); */
  if (bomb->bomb_weakreflist != NULL)
    PyObject_ClearWeakRefs((PyObject*)bomb);
  bomb_clear(bomb);
  (((PyObject*)(bomb))->ob_type)->tp_free((PyObject*)bomb);
}

static PyMemberDef bomb_members[] = {
  {"type",        T_OBJECT_EX, offsetof(PyBombObject, bomb_type), 0},
  {"value",       T_OBJECT_EX, offsetof(PyBombObject, bomb_value), 0},
  {"traceback",   T_OBJECT_EX, offsetof(PyBombObject, bomb_traceback), 0},
  {0},
};

static PyMethodDef bomb_methods[] = {
  {0, 0, 0, 0},
};

PyDoc_VAR(bomb__doc__) = PyDoc_STR("It is an emulated bomb.");

static PyTypeObject PyBombObject_Type = {
  PyObject_HEAD_INIT(NULL)
  0,                      /*ob_size*/
  "bomb",                 /*tp_name*/
  sizeof(PyBombObject),        /*tp_basicsize*/
  0,                        /*tp_itemsize*/
  (destructor)bomb_dealloc, /*tp_dealloc*/
  0,                        /*tp_print*/
  0,                        /*tp_getattr*/
  0,                        /*tp_setattr*/
  0,                        /*tp_compare*/
  0,                        /*tp_repr*/
  0,                        /*tp_as_number*/
  0,                        /*tp_as_sequence*/
  0,                        /*tp_as_mapping*/
  0,                        /*tp_hash*/
  0,                      /*tp_call*/
  0,                      /*tp_str*/
  PyObject_GenericGetAttr,/*tp_getattro*/
  PyObject_GenericSetAttr,/*tp_setattro*/
  0,                      /*tp_as_buffer*/
  Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE | Py_TPFLAGS_HAVE_GC,  /*tp_flags*/
  bomb__doc__,            /*tp_doc*/
  (traverseproc)bomb_traverse,  /*tp_traverse*/
  (inquiry)bomb_clear,    /*tp_clear*/
  0,                      /*tp_richcompare*/
  offsetof(PyBombObject, bomb_weakreflist), /* tp_weaklistoffset */
  0,                      /*tp_iter*/
  0,                      /*tp_iternext*/
  bomb_methods,           /*tp_methods*/
  bomb_members,           /*tp_members*/
  0,                      /*tp_getset*/
  0,                      /*tp_base*/
  0,                      /*tp_dict*/
  0,                      /*tp_descr_get*/
  0,                      /*tp_descr_set*/
  0,                      /*tp_dictoffset*/
  (initproc)bomb_init,    /*tp_init*/
  0,                      /*tp_alloc*/
  bomb_new,               /*tp_new*/
  0,                      /*tp_free*/  /* _PyObject_GC_Del */
  0,                      /*tp_is_gc*/
};

static PyObject *tasklet_new(PyTypeObject *type,
                             PyObject *args,
                             PyObject *kwargs) {
  PyTaskletObject *tasklet;
  PyObject *tmp;
  if (NULL != (tasklet = (PyTaskletObject*)type->tp_alloc(type, 0))) {
    tasklet->tasklet_weakreflist = NULL;
    tasklet->next = NULL;
    tasklet->prev = NULL;
    tasklet->tempval = NULL;
    (void)args;
    (void)kwargs;

    tmp = tasklet->tempval;
    Py_INCREF(Py_None);
    tasklet->tempval = Py_None;
    Py_XDECREF(tmp);
  }
  return (PyObject*)tasklet;
}

static int tasklet_traverse(PyTaskletObject *tasklet, visitproc visit, void *arg) {
  Py_VISIT(tasklet->next);
  Py_VISIT(tasklet->prev);
  Py_VISIT(tasklet->tempval);
  return 0;
}

static void tasklet_clear(PyTaskletObject *tasklet) {
  Py_CLEAR(tasklet->next);
  Py_CLEAR(tasklet->prev);
  Py_CLEAR(tasklet->tempval);
}

static void tasklet_dealloc(PyTaskletObject *tasklet) {
  if (tasklet->tasklet_weakreflist != NULL)
    PyObject_ClearWeakRefs((PyObject*)tasklet);
  tasklet_clear(tasklet);
  (((PyObject*)(tasklet))->ob_type)->tp_free((PyObject*)tasklet);
}

static PyTypeObject PyTaskletObject_Type;

static PyObject *tasklet_get_next(PyTaskletObject *tasklet) {
  PyObject *ret = Py_None;
  if (tasklet->next != NULL &&
      PyObject_TypeCheck(tasklet->next, &PyTaskletObject_Type))
    ret = (PyObject *) tasklet->next;
  Py_INCREF(ret);
  return ret;
}

static PyObject *tasklet_get_prev(PyTaskletObject *tasklet) {
  PyObject *ret = Py_None;
  if (tasklet->prev != NULL &&
      PyObject_TypeCheck(tasklet->prev, &PyTaskletObject_Type))
    ret = (PyObject *) tasklet->prev;
  Py_INCREF(ret);
  return ret;
}

static PyObject *tasklet_get_tempval(PyTaskletObject *tasklet) {
  PyObject *ret = Py_None;
  if (tasklet->tempval != NULL)
    ret = tasklet->tempval;
  Py_INCREF(ret);
  return ret;
}

static int tasklet_set_next(PyTaskletObject *tasklet, PyObject *value) {
  PyObject *tmp;
  if (value == Py_None) {
    Py_XDECREF(tasklet->next);
    tasklet->next = NULL;
    return 0;
  }
  if (!PyObject_TypeCheck(value, &PyTaskletObject_Type)) {
    PyErr_Format(PyExc_TypeError,
        "Argument next has incorrect type (expected %s, got %s)",
        PyTaskletObject_Type.tp_name, value->ob_type->tp_name);
    return -1;
  }
  tmp = (PyObject*)tasklet->next;
  Py_INCREF(value);
  tasklet->next = (PyTaskletObject*)value;
  Py_XDECREF(tmp);
  return 0;
}

static int tasklet_set_prev(PyTaskletObject *tasklet, PyObject *value) {
  PyObject *tmp;
  if (value == Py_None) {
    Py_XDECREF(tasklet->prev);
    tasklet->prev = NULL;
    return 0;
  }
  if (!PyObject_TypeCheck(value, &PyTaskletObject_Type)) {
    PyErr_Format(PyExc_TypeError,
        "Argument prev has incorrect type (expected %s, got %s)",
        PyTaskletObject_Type.tp_name, value->ob_type->tp_name);
    return -1;
  }
  tmp = (PyObject*)tasklet->prev;
  Py_INCREF(value);
  tasklet->prev = (PyTaskletObject*)value;
  Py_XDECREF(tmp);
  return 0;
}

static int tasklet_set_tempval(PyTaskletObject *tasklet, PyObject *value) {
  PyObject *tmp = (PyObject*)tasklet->tempval;
  Py_INCREF(value);
  tasklet->tempval = value;
  Py_XDECREF(tmp);
  return 0;
}

static PyGetSetDef tasklet_getset[] = {
  /* Doing a PyGetSetDef instead of a PyMemberDef for tempval, because of
   * inheritance (other classes inheriting PyTaskletObject.
   */
  {"tempval", (getter)tasklet_get_tempval, (setter)tasklet_set_tempval,
   "the next tasklet in a a circular list of tasklets."},
  {"next", (getter)tasklet_get_next, (setter)tasklet_set_next,
   "the next tasklet in a a circular list of tasklets."},
  {"prev", (getter)tasklet_get_prev, (setter)tasklet_set_prev,
   "the next tasklet in a a circular list of tasklets."},
};

static PyMethodDef tasklet_methods[] = {
  {0, 0, 0, 0},
};

PyDoc_VAR(tasklet__doc__) = PyDoc_STR("It is an emulated tasklet.");

static PyTypeObject PyTaskletObject_Type = {
  PyObject_HEAD_INIT(NULL)
  0,                      /*ob_size*/
  "tasklet",              /*tp_name*/
  sizeof(PyTaskletObject),        /*tp_basicsize*/
  0,                        /*tp_itemsize*/
  (destructor)tasklet_dealloc, /*tp_dealloc*/
  0,                        /*tp_print*/
  0,                        /*tp_getattr*/
  0,                        /*tp_setattr*/
  0,                        /*tp_compare*/
  0,                        /*tp_repr*/
  0,                        /*tp_as_number*/
  0,                        /*tp_as_sequence*/
  0,                        /*tp_as_mapping*/
  0,                        /*tp_hash*/
  0,                      /*tp_call*/
  0,                      /*tp_str*/
  PyObject_GenericGetAttr,/*tp_getattro*/
  PyObject_GenericSetAttr,/*tp_setattro*/
  0,                      /*tp_as_buffer*/
  Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE | Py_TPFLAGS_HAVE_GC,  /*tp_flags*/
  tasklet__doc__,            /*tp_doc*/
  (traverseproc)tasklet_traverse,  /*tp_traverse*/
  (inquiry)tasklet_clear,    /*tp_clear*/
  0,                      /*tp_richcompare*/
  offsetof(PyTaskletObject, tasklet_weakreflist), /* tp_weaklistoffset */
  0,                      /*tp_iter*/
  0,                      /*tp_iternext*/
  tasklet_methods,        /*tp_methods*/
  0,                      /*tp_members*/
  tasklet_getset,         /*tp_getset*/
  0,                      /*tp_base*/
  0,                      /*tp_dict*/
  0,                      /*tp_descr_get*/
  0,                      /*tp_descr_set*/
  0,                      /*tp_dictoffset*/
  0,                      /*tp_init*/
  0,                      /*tp_alloc*/
  tasklet_new,            /*tp_new*/
  0,                      /*tp_free*/  /* _PyObject_GC_Del */
  0,                      /*tp_is_gc*/
};

static PyObject *stackless_module = NULL;

static inline PyTaskletObject *PyStackless_GetCurrent(void) {
  PyObject *tasklet;
  tasklet = PyObject_GetAttrString(stackless_module, "current");
  if (tasklet != NULL) {
    if (!PyObject_TypeCheck(tasklet, &PyTaskletObject_Type)) {
      PyErr_Format(PyExc_TypeError,
          "current tasklet has incorrect type (expected %s, got %s)",
          PyTaskletObject_Type.tp_name, tasklet->ob_type->tp_name);
      Py_DECREF(tasklet);
      return NULL;
    }
  }
  return (PyTaskletObject*)tasklet;
}
  
static inline PyObject *PyStackless_Schedule(PyObject *retval, int remove) {
  PyObject *function, *args;
  function = PyObject_GetAttrString(
      stackless_module, remove ? "schedule_remove" : "schedule");
  if (function == NULL) return NULL;
  if (NULL == (args = PyTuple_New(1))) {
    Py_DECREF(function);
    return NULL;
  }
  Py_INCREF(retval);
  PyTuple_SET_ITEM(args, 0, retval);
  /* TODO(pts): Who has to check the type of function? */
  retval = PyObject_CallObject(function, args);
  Py_DECREF(function);
  Py_DECREF(args);
  return retval;
}

static inline int PyStackless_GetRunCount(void) {
  int retint;
  PyObject *function, *retval;
  function = PyObject_GetAttrString(stackless_module, "getruncount");
  if (function == NULL) return -1;
  retval = PyObject_CallObject(function, NULL);
  Py_DECREF(function);
  if (retval == NULL) return -1;
  if (!PyInt_Check(retval)) {
    Py_DECREF(retval);
    return -1;
  }
  retint = PyInt_AsLong(retval);
  Py_DECREF(retval);
  return retint;
}

static inline int PyTasklet_Insert(PyTaskletObject *tasklet_obj) {
  PyObject *function, *retval;
  function = PyObject_GetAttrString((PyObject*)tasklet_obj, "insert");
  if (function == NULL) return -1;
  retval = PyObject_CallObject(function, NULL);
  Py_DECREF(function);
  if (retval == NULL) return -1;
  Py_DECREF(retval);
  return 0;
}

static inline int PyTasklet_Remove(PyTaskletObject *tasklet_obj) {
  PyObject *function, *retval;
  function = PyObject_GetAttrString((PyObject*)tasklet_obj, "remove");
  if (function == NULL) return -1;
  retval = PyObject_CallObject(function, NULL);
  Py_DECREF(function);
  if (retval == NULL) return -1;
  Py_DECREF(retval);
  return 0;
}

static inline int PyTasklet_Kill(PyTaskletObject *tasklet_obj) {
  PyObject *function, *retval;
  function = PyObject_GetAttrString((PyObject*)tasklet_obj, "kill");
  if (function == NULL) return -1;
  retval = PyObject_CallObject(function, NULL);
  Py_DECREF(function);
  if (retval == NULL) return -1;
  Py_DECREF(retval);
  return 0;
}

static inline int PyTasklet_Alive(PyTaskletObject *tasklet_obj) {
  /* TODO(pts): Let Pyrex report a proper traceback for a TypeError
   * here (now the traceback seems to be completely bogus).
   */
  int retint;
  PyObject *retval;
  retval = PyObject_GetAttrString((PyObject*)tasklet_obj, "alive");
  if (retval == NULL) return -1;
  if (!PyInt_Check(retval)) {
    Py_DECREF(retval);
    return -1;
  }
  retint = PyInt_AsLong(retval);
  Py_DECREF(retval);
  return retint;
}

static inline int PyTasklet_GetBlocked(PyTaskletObject *tasklet_obj) {
  int retint;
  PyObject *retval;
  retval = PyObject_GetAttrString((PyObject*)tasklet_obj, "blocked");
  if (retval == NULL) return -1;
  if (!PyInt_Check(retval)) {
    Py_DECREF(retval);
    return -1;
  }
  retint = PyInt_AsLong(retval);
  Py_DECREF(retval);
  return retint;
}

static struct PyMethodDef stmin_methods[] = {
  {0, 0, 0, 0}
};

PyDoc_VAR(stmin__doc__) = PyDoc_STR("A simple method.");

#undef initcoio
PyMODINIT_FUNC GENERATED_initcoio(void);
PyMODINIT_FUNC initcoio(void);
PyMODINIT_FUNC initcoio(void) {
  PyObject *all_modules, *mod;
  PyObject *greenstackless_module;

  if (NULL == (all_modules = PySys_GetObject("modules"))) return;
  if (NULL != (stackless_module =
               PyDict_GetItemString(all_modules, "stackless"))) {
    if (PyObject_HasAttrString(stackless_module, "is_greenstackless") != 1) {
      Py_DECREF(stackless_module);
      PyErr_SetString(PyExc_AssertionError, "stackless already loaded"
                      " -- are you loading syncless.coio in the "
                      "non-Stackless Python it was compiled for?");
      return;
    }
    Py_DECREF(stackless_module);
  }
  mod = Py_InitModule3("syncless.coio_greenstackless_helper",
                       stmin_methods, stmin__doc__);
  if (!mod) {
    return;
  }

  if (PyType_Ready(&PyBombObject_Type) < 0) {
    return;
  }
  Py_INCREF(&PyBombObject_Type);
  PyModule_AddObject(mod, "bomb", (PyObject*)&PyBombObject_Type);

  if (PyType_Ready(&PyTaskletObject_Type) < 0) {
    return;
  }
  Py_INCREF(&PyTaskletObject_Type);
  PyModule_AddObject(mod, "tasklet", (PyObject*)&PyTaskletObject_Type);

  if (NULL != (stackless_module =
               PyDict_GetItemString(all_modules, "syncless.greenstackless"))) {
    PyObject *function, *retval;
    function = PyObject_GetAttrString(stackless_module, "_coio_rebase");
    Py_DECREF(stackless_module);
    if (function == NULL) return;
    retval = PyObject_CallFunction(function, "O", mod);
    Py_DECREF(function);
    if (retval == NULL) return;
    Py_DECREF(retval);
  }

  greenstackless_module = PyImport_ImportModule("syncless.greenstackless");
  if (!greenstackless_module) {
    return;
  }
    
  if (0 !=
      PyDict_SetItemString(all_modules, "stackless", greenstackless_module)) {
    Py_DECREF(greenstackless_module);
    return;
  }
  stackless_module = greenstackless_module;  /* So omit Py_DECREF. */
  GENERATED_initcoio();
}
#define initcoio GENERATED_initcoio

#endif  /* COIO_CO_USE_GREENLET */
