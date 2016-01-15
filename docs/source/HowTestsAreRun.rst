=================
How tests are run
=================

When running tests Avocado-VT will:

1) Get a dict with test parameters
2) Based on these params, prepare the environment - create or destroy vm
   instances, create/check disk images, among others
3) Execute the test itself, that will use several of the params defined to
   carry on with its operations, that usually involve:
4) If a test did not raise an exception, it PASSed
5) If a test raised a TestFail exception, it FAILed. Otherwise, it ERRORed.
6) Based on what happened during the test, perform cleanup actions, such as
   killing vms, and remove unused disk images.

The list of parameters is obtained by parsing a set of configuration files
The command line options usually modify even further the parser file, so
we can introduce new data in the config set.
