================================
Writing your own avocado VT test
================================

In this article, we'll talk about:

#. Where the test files are located
#. Write a simple test file
#. Try out your new test, send it to the mailing list

Write our own 'uptime' test - Step by Step procedure
----------------------------------------------------

Now, let's go and write our uptime test, which only purpose in life is
to pick up a living guest, connect to it via ssh, and return its uptime.

#. First we need to locate our provider directory. It's inside Avocado
   `data` directory (`avocado config --datadir`), usually in
   `~/avocado/data/avocado-vt`. We are going to write a generic `tp-qemu`
   test, so let's move into the right git location::

    $ cd $AVOCADO_DATA/avocado-vt/test-providers.d/downloads/io-github-autotest-qemu

#. Our uptime test won't need any qemu specific feature. Thinking about
   it, we only need a vm object and establish an ssh session to it, so we
   can run the command. So we can store our brand new test under
   ``generic/tests``::

    $ touch generic/tests/uptime.py
    $ git add generic/tests/uptime.py

#. OK, so that's a start. So, we have *at least* to implement a
   function ``run``. Let's start with it and just put the keyword
   pass, which is a no op. Our test will be like:

   .. code-block:: python

       def run(test, params, env):
           """
           Docstring describing uptime.
           """
           pass

#. Now, what is the API we need to grab a VM from our test environment?
   Our env object has a method, ``get_vm``, that will pick up a given vm
   name stored in our environment. Some of them have aliases. ``main_vm``
   contains the name of the main vm present in the environment, which
   is, most of the time, ``vm1``. ``env.get_vm`` returns a vm object, which
   we'll store on the variable vm. It'll be like this:

   .. code-block:: python

       def run(test, params, env):
           """
           Docstring describing uptime.
           """
           vm = env.get_vm(params["main_vm"])

#. A vm object has lots of interesting methods, which we plan on documenting
   them more thoroughly, but for
   now, we want to ensure that this VM is alive and functional, at least
   from a qemu process standpoint. So, we'll call the method
   ``verify_alive()``, which will verify whether the qemu process is
   functional and if the monitors, if any exist, are functional. If any
   of these conditions are not satisfied due to any problem, an
   exception will be thrown and the test will fail. This requirement is
   because sometimes due to a bug the vm process might be dead on the
   water, or the monitors are not responding:

   .. code-block:: python

       def run(test, params, env):
           """
           Docstring describing uptime.
           """
           vm = env.get_vm(params["main_vm"])
           vm.verify_alive()

#. Next step, we want to log into the vm. The vm method that does return
   a remote session object is called ``wait_for_login()``, and as one of
   the parameters, it allows you to adjust the timeout, that is, the
   time we want to wait to see if we can grab an ssh prompt. We have top
   level variable ``login_timeout``, and it is a good practice to
   retrieve it and pass its value to ``wait_for_login()``, so if for
   some reason we're running on a slower host, the increase in one
   variable will affect all tests. Note that it is completely OK to just
   override this value, or pass nothing to ``wait_for_login()``, since
   this method does have a default timeout value. Back to business,
   picking up login timeout from our dict of parameters:

   .. code-block:: python

       def run(test, params, env):
           """
           Docstring describing uptime.
           """
           vm = env.get_vm(params["main_vm"])
           vm.verify_alive()
           timeout = float(params.get("login_timeout", 240))


#. Now we'll call ``wait_for_login()`` and pass the timeout to it,
   storing the resulting session object on a variable named session:

   .. code-block:: python

       def run(test, params, env):
           """
           Docstring describing uptime.
           """
           vm = env.get_vm(params["main_vm"])
           vm.verify_alive()
           timeout = float(params.get("login_timeout", 240))
           session = vm.wait_for_login(timeout=timeout)


#. Avocado-VT will do its best to grab this session, if it can't due
   to a timeout or other reason it'll throw a failure, failing the test.
   Assuming that things went well, now you have a session object, that
   allows you to type in commands on your guest and retrieve the
   outputs. So most of the time, we can get the output of these commands
   through the method ``cmd()``. It will type in the command, grab the
   stdin and stdout, return them so you can store it in a variable, and
   if the exit code of the command is != 0, it'll throw a
   aexpect.ShellError?. So getting the output of the unix command uptime
   is as simple as calling ``cmd()`` with 'uptime' as a parameter and
   storing the result in a variable called uptime:

   .. code-block:: python

       def run(test, params, env):
           """
           Docstring describing uptime.
           """
           vm = env.get_vm(params["main_vm"])
           vm.verify_alive()
           timeout = float(params.get("login_timeout", 240))
           session = vm.wait_for_login(timeout=timeout)
           uptime = session.cmd('uptime')

   .. warning:: Some guests OS's do not respect terminal ``echo`` setting,
      corrupting the output. There are some workaround described in
      github `issue#231 <https://github.com/avocado-framework/avocado-vt/issues/231>`_.

#. If you want to just print this value so it can be seen on the test
   logs, just log the value of uptime using the logging library. Since
   that is all we want to do, we may close the remote connection, to
   avoid ssh/rss sessions lying around your test machine, with the
   method ``close()``.

   .. code-block:: python

       def run(test, params, env):
           """
           Docstring describing uptime.
           """
           vm = env.get_vm(params["main_vm"])
           vm.verify_alive()
           timeout = float(params.get("login_timeout", 240))
           session = vm.wait_for_login(timeout=timeout)
           uptime = session.cmd('uptime')
           logging.info("Guest uptime result is: %s", uptime)
           session.close()

#. Note that all failures that might happen here are implicitly handled
   by the methods called. If a test went from its beginning to its end
   without unhandled exceptions, avocado assumes the test automatically
   as **PASS**, *no need to mark a test as explicitly passed*. If you
   have explicit points of failure, for more complex tests, you might
   want to mark it explicitly. ``test.cancel`` makes the test **CANCEL**
   (it is a new feature which not supported in avocado 36lts, you may
   want to use ``test.skip`` to make the test **SKIP** to achieve the
   similar purpose), ``test.error`` makes the test **Error**, and
   ``test.fail`` makes the test **Fail**. And, in recent Avocado version
   (since commit 7ecf09fa), three exceptions: ``TestFail``, ``TestError``,
   and ``TestCancel`` were added to avocado namespace, so you can import
   and use them appropriately. Note, people should not import ``exceptions``
   from ``avocado.core`` to raise them in test case, see `avocado doc <http://avocado-framework.readthedocs.io/en/latest/api/core/avocado.core.html>`_
   for more details. *BTW, check the uptime makes no sense, but let's continue
   this example for test status explanation*:

   .. code-block:: python
      :emphasize-lines: 16,18,20

       def run(test, params, env):
           """
           Docstring describing uptime.
           """
           vm = env.get_vm(params["main_vm"])
           vm.verify_alive()
           timeout = float(params.get("login_timeout", 240))
           session = vm.wait_for_login(timeout=timeout)
           uptime = session.cmd('uptime')
           logging.info("Guest uptime result is: %s", uptime)
           session.close()
           expected_cancel_msg = '0 min'
           expected_err_msg = '1 day'
           expected_fail_msg = '10 days'
           if expected_cancel_msg in uptime:
               test.cancel('Cancel message')
           if expected_err_msg in uptime:
               test.error('Error message')
           if expected_fail_msg in uptime:
               test.fail('Fail message')

#. Now, I deliberately introduced a bug on this code just to show you
   guys how to use some tools to find and remove trivial bugs on your
   code. I strongly encourage you guys to check your code with the `inspektor`
   tool. This tool uses pylint to catch bugs on test code. You can install
   inspektor by adding the COPR repo https://copr.fedoraproject.org/coprs/lmr/Autotest/
   and doing ::

    $ yum install inspektor

   After you're done, you can run it::

        $ inspekt lint generic/tests/uptime.py
        ************* Module generic.tests.uptime
        E0602: 10,4: run: Undefined variable 'logging'
        Pylint check fail: generic/tests/uptime.py
        Syntax check FAIL

#. Ouch. So there's this undefined variable called logging on line 10 of
   the code. It's because I forgot to import the logging library, which
   is a python library to handle info, debug, warning messages. Let's Fix it
   and the code becomes:

   .. code-block:: python

       import logging

       def run(test, params, env):
           """
           Docstring describing uptime.
           """
           vm = env.get_vm(params["main_vm"])
           vm.verify_alive()
           timeout = float(params.get("login_timeout", 240))
           session = vm.wait_for_login(timeout=timeout)
           uptime = session.cmd("uptime")
           logging.info("Guest uptime result is: %s", uptime)
           session.close()

#. Let's re-run ``inspektor`` to see if it's happy with the code
   generated::

        $ inspekt lint generic/tests/uptime.py
        Syntax check PASS

#. So we're good. Nice! Now, as good indentation does matter to python,
   `inspekt indent` will fix indentation problems, and cut trailing
   whitespaces on your code. Very nice for tidying up your test before
   submission::

        $ inspekt indent generic/tests/uptime.py

#. Now, you can test your code. When listing the qemu tests your new test should
   appear in the list (or shouldn't it?)::

        $ avocado list uptime

#. There is one more thing to do. Avocado-vt does not walk the directories,
   it uses `Cartesian config` to define test and all possible variants of
   tests. To add our test to `Cartesian config` we need yet another file::

    $ touch generic/tests/cfg/uptime.cfg
    $ git add generic/tests/cfg/uptime.cfg

#. The file might look like this::

    - uptime:
        virt_test_type = qemu libvirt
        type = uptime

   where the `virt_test_type` specifies what backends can run this test and
   `type` specifies the test file. The `.py` will be appended and it'll be
   searched for in the usual location.

#. For the second time, let's try to discover the test::

    $ avocado list uptime

#. OK still not there. We need to propagate the change to the actual config
   by running `vt-bootstrap`::

    $ avocado vt-bootstrap

#. And now you'll finally see the test::

    $ avocado list uptime

#. Now, you can run your test to see if everything went well::

        $ avocado run --vt-type qemu uptime

#. OK, so now, we have something that can be git committed and sent to
   the mailing list (partial):

   .. code-block:: diff

        diff --git a/generic/tests/uptime.py b/generic/tests/uptime.py
        index e69de29..65d46fa 100644
        --- a/tests/uptime.py
        +++ b/tests/uptime.py
        @@ -0,0 +1,13 @@
        +import logging
        +
        +def run(test, params, env):
        +    """
        +    Docstring describing uptime.
        +    """
        +    vm = env.get_vm(params["main_vm"])
        +    vm.verify_alive()
        +    timeout = float(params.get("login_timeout", 240))
        +    session = vm.wait_for_login(timeout=timeout)
        +    uptime = session.cmd("uptime")
        +    logging.info("Guest uptime result is: %s", uptime)
        +    session.close()

#. Oh, we forgot to add a decent docstring description. So doing it:

   .. code-block:: python

       import logging

       def run(test, params, env):

           """
           Uptime test for virt guests:

           1) Boot up a VM.
           2) Establish a remote connection to it.
           3) Run the 'uptime' command and log its results.

           :param test: QEMU test object.
           :param params: Dictionary with the test parameters.
           :param env: Dictionary with test environment.
           """

           vm = env.get_vm(params["main_vm"])
           vm.verify_alive()
           timeout = float(params.get("login_timeout", 240))
           session = vm.wait_for_login(timeout=timeout)
           uptime = session.cmd("uptime")
           logging.info("Guest uptime result is: %s", uptime)
           session.close()

#. git commit signing it, put a proper description, then send it with
   git send-email. Profit!
