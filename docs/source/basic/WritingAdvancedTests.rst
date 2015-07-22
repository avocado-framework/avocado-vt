
Writing a more advanced test
============================

Now that you wrote your first simple test, we'll try some more involved
examples. First, let's talk about some useful APIs and concepts:

As virt-tests evolved, a number of libraries were written to help test writers.
Let's see what some of them can do:

1) virttest.data_dir -> Has functions to get paths for resource files. One of the
   most used functions is data_dir.get_data_dir(), that returns the path
   shared/data, which helps you to get files.

::

    from virttest import data_dir

What's available upfront
------------------------

Very frequently we may get values from the config
set. All virt tests take 3 params:

   test -> Test object
   params -> Dict with current test params
   env -> Environment file being used for the test job

You might pick any parameter using

::

    variable_name = params.get("param_name", default_value)

You can update the parameters using 