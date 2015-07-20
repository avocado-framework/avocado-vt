=========
Profiling
=========

What is profiling
-----------------

Profiling, by its definition (see `this wikipedia
article <http://en.wikipedia.org/wiki/Profiling_(computer_programming)>`_
for a non formal introduction), is to run an analysis tool to inspect
the behavior of a certain property of the system (be it memory, CPU
consumption or any other).

How autotest can help with profiling?
-------------------------------------

Autotest provides support for running profilers during the execution of
tests, so we know more about a given system resource. For the ``kvm``
test, our first idea of profiling usage was to run the kvm_stat
program, that usually ships with kvm, to provide data useful for
debugging. kvm_stat provides the number of relevant kvm events every
time it is called, so by the end of a virt-test test we end up with a
long list of information like this one:

::

     kvm_ack_i  kvm_age_p   kvm_apic  kvm_apic_  kvm_apic_  kvm_async  kvm_async  kvm_async  kvm_async  kvm_cpuid     kvm_cr  kvm_emula  kvm_entry   kvm_exit  kvm_exit(  kvm_exit(  kvm_exit(  kvm_exit(  kvm_exit(  kvm_exit(  kvm_exit(  kvm_exit(  kvm_exit(  kvm_exit(  kvm_exit(  kvm_exit(  kvm_exit(  kvm_exit(  kvm_exit(  kvm_exit(  kvm_exit(  kvm_exit(  kvm_exit(  kvm_exit(  kvm_exit(  kvm_exit(  kvm_exit(  kvm_exit(  kvm_exit(  kvm_exit(  kvm_exit(  kvm_exit(  kvm_exit(  kvm_exit(  kvm_exit(  kvm_exit(  kvm_exit(  kvm_exit(  kvm_exit(  kvm_exit(  kvm_exit(    kvm_fpu  kvm_hv_hy  kvm_hyper  kvm_inj_e  kvm_inj_v  kvm_invlp  kvm_ioapi   kvm_mmio  kvm_msi_s    kvm_msr  kvm_neste  kvm_neste  kvm_neste  kvm_neste  kvm_neste  kvm_page_  kvm_pic_s    kvm_pio  kvm_set_i  kvm_skini  kvm_try_a  kvm_users
             1         54         11          5          0          0          0          0          0          0          3         15         28         28         11          0          3          0          0          0          1          2          5          0          0          5          0          0          0          0          0          0          0          1          0          0          0          0          0          0          0          0          0          0          0          0          0          0          0          0          0          4          0          0          0          5          0          2         11          0          0          0          0          0          0          0          0          2          5          2          0          0          5

How to control the execution of profilers ?
-------------------------------------------

Profiling in virt-test is controlled through configuration files. You
can set the profilers that are going to run by setting the variable
``profilers``. On ``tests_base.cfg.sample``, the section of the file
that sets the profilers that run by default looks like this:

::

    # Profilers. You can add more autotest profilers (see list on client/profilers)
    # to the line below. You can also choose to remove all profilers so no profiling
    # will be done at all.
    profilers = kvm_stat

How to add a profiler?
----------------------

So, say you want to run the perf profiler in addition to kvm_stat. You
can just edit that place and put 'perf' right next to it:

::

    # Profilers. You can add more autotest profilers (see list on client/profilers)
    # to the line below. You can also choose to remove all profilers so no profiling
    # will be done at all.
    profilers = kvm_stat perf

How to remove all profilers (including kvm_stat)?
--------------------------------------------------

If you want no profiling at all for your tests, profilers can be changed
to be an empty string:

::

    # Profilers. You can add more autotest profilers (see list on client/profilers)
    # to the line below. You can also choose to remove all profilers so no profiling
    # will be done at all.
    profilers =

Of course, the config system makes it easy to override the value of
*any* param for your test variable, so you can have fine grained
control of things. Say you don't want to run profilers on your new
'crazy_test' variant, which you have developed. Easy:

::

        - crazy_test:
            type = crazy_test
            profilers =

So this will turn of profilers just for this particular test of yours.

