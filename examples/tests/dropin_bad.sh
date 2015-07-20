#!/bin/bash

# difficulty: simplest
# This test tries to execute "missing_command", which shouldn't be installed
# thus this test should FAIL.

# Put this file into $virttest/dropin directory, allow execution rights and
# execute runner with -run-dropin
# Please note that all dropin tests are executed.
missing_command
