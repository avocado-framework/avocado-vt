#!/bin/bash
set -eux

readonly test_suite="${TEST_SUITE:-/root/avocado-i2n-libs/tp_folder}"
readonly test_results="${TEST_RESULTS:-/root/avocado/job-results}"
readonly i2n_config="${I2N_CONFIG:-/etc/avocado/conf.d/i2n.conf}"

# local environment preparation
echo
echo "Configure locally the current plugin source and prepare to run"
# TODO: local installation does not play well with external pre-installations - provide custom container instead
#pip install -e .
# change default avocado settings to our preferences for an integration run
cat >/etc/avocado/avocado.conf <<EOF
[runner.output]
# Whether to display colored output in terminals that support it
colored = True
# Whether to force colored output to non-tty outputs (e.g. log files)
# Allowed values: auto, always, never
color = always

[run]
# LXC and remote spawners require manual status server address
status_server_uri = 192.168.254.254:8080
status_server_listen = 192.168.254.254:8080

[spawner.lxc]
slots = ['c101', 'c102', 'c103', 'c104', 'c105']

[spawner.remote]
slots = ['c101', 'c102', 'c103', 'c104', 'c105']
EOF
mkdir -p /etc/avocado/conf.d
# TODO: use VT's approach to register the plugin config
if [ ! -f /etc/avocado/conf.d/i2n.conf ]; then
    ln -s ~/avocado-i2n-libs/avocado_i2n/conf.d/i2n.conf "${i2n_config}"
fi
sed -i "s#suite_path = .*#suite_path = ${test_suite}#" "${i2n_config}"
rm ${HOME}/avocado_overwrite_* -fr
rm -fr /mnt/local/images/swarm/*
rm -fr /mnt/local/images/shared/vm1-* /mnt/local/images/shared/vm2-*

# minimal other dependencies for the integration run
dnf install -y python3-coverage python3-lxc

# minimal effect runs
echo
echo "Perform minimal effect steps (run minimal noop/list/run tools)"
# fully avocado-integrated plugin entry points
coverage run --append --source=avocado_i2n $(which avocado) list --auto "only=tutorial1"
coverage run --append --source=avocado_i2n $(which avocado) run --auto "only=tutorial1 dry_run=yes"
# minimal manual steps
coverage run --append --source=avocado_i2n $(which avocado) manu setup=noop
coverage run --append --source=avocado_i2n $(which avocado) manu setup=list

# full integration run
echo
echo "Perform a full sample test suite run"
avocado_cmd="coverage run --append --source=avocado_i2n $(which avocado) manu"
test_slots="net1,net2,net3,net4,net5"
$avocado_cmd setup=run nets=$test_slots only=leaves only_vm1=

# custom checks
echo
echo "Check for correctly included tests"
test $(ls -A1q "$test_results/latest/test-results" | grep implicit_both | wc -l) == 2 || (echo "Incorrect number cloned 1-level tutorial tests" && exit 1)
test $(ls -A1q "$test_results/latest/test-results" | grep tutorial_get.implicit_both.guisetup.noop | wc -l) == 1 || (echo "Incorrect number of cloned 1-level tutorial tests" && exit 1)
test $(ls -A1q "$test_results/latest/test-results" | grep tutorial_get.implicit_both.guisetup.clicked | wc -l) == 1 || (echo "Incorrect number of cloned 1-level tutorial tests" && exit 1)
test $(ls -A1q "$test_results/latest/test-results" | grep tutorial_finale | wc -l) == 2 || (echo "Incorrect number of cloned 2-level tutorial tests" && exit 1)
test $(ls -A1q "$test_results/latest/test-results" | grep tutorial_finale.getsetup.guisetup.noop | wc -l) == 1 || (echo "Incorrect number of cloned 2-level tutorial tests" && exit 1)
test $(ls -A1q "$test_results/latest/test-results" | grep tutorial_finale.getsetup.guisetup.clicked | wc -l) == 1 || (echo "Incorrect number of cloned 2-level tutorial tests" && exit 1)

echo
echo "Check if all containers have identical and synced states after the run"
ims="mnt/local/images"
containers="$(printf $test_slots | sed "s/,/ /g" | sed "s/net/10/g")"
for cid in $containers; do
    diff -r /$ims/c101/rootfs/$ims /$ims/c$cid/rootfs/$ims -x el8-64* -x f40-64* -x win10-64* -x vm3 || (echo "Different states found at ${cid}" && exit 1)
done
# verify that either vm1/vm2 shared pool doesn't exist or is empty for the validity of our tests
ls -A1q /mnt/local/images/shared/vm1-* 2>/dev/null | grep -q . && (echo "Unexpected vm1 images in the shared pool" && exit 1)
ls -A1q /mnt/local/images/shared/vm2-* 2>/dev/null | grep -q . && (echo "Unexpected vm2 images in the shared pool" && exit 1)
ls -A1q /mnt/local/images/shared/vm3* | grep -q . || (echo "Missing vm3 images in the shared pool" && exit 1)
ls -A1q "$test_results/latest/test-results" | grep -q CentOS | grep -q net5 && (echo "The worker net5 should never run CentOS tests" && exit 1)
ls -A1q "$test_results/latest/test-results" | grep -q Win7 | grep -q net5 && (echo "The worker net5 should never run Win7 tests" && exit 1)
ls -A1q "$test_results/latest/test-results" | grep -q Fedora | grep -q net5 && (echo "The worker net5 should still run Fedora tests" && exit 1)
full_run_job=$(basename $(realpath "$test_results"/latest))

echo
echo "Check graph verbosity and and simple test reruns compatibility"
$avocado_cmd setup=run nets=$test_slots only=tutorial1 only_vm1= max_tries=5 cartgraph_verbose_level=0
test $(ls -A1q "$test_results/latest/test-results" | grep -v by-status | wc -l) == 10 || (echo "Unexpected or missing tests replayed" && exit 1)
ls -A1q "$test_results/latest/test-results" | grep -q CentOS | grep -q net5 && (echo "The worker net5 should never run CentOS tests" && exit 1)
ls -A1q "$test_results/latest/test-results" | grep -q Win7 | grep -q net5 && (echo "The worker net5 should never run Win7 tests" && exit 1)
ls -A1q "$test_results/latest/test-results" | grep -q Fedora | grep -q net5 && (echo "The worker net5 should still run Fedora tests" && exit 1)
test -f "$test_results"/latest/cg_*.svg || (echo "Missing minimal main graph dump" && exit 1)
test -d "$test_results"/latest/graph_* || (echo "Missing graph dump directory" && exit 1)
find "$test_results"/latest/graph_*/cg_*.svg > /dev/null || (echo "Missing detailed graph dumps" && exit 1)

echo
echo "Check replay and overall test reruns behave as expected"
$avocado_cmd setup=run nets=$test_slots only=leaves replay=$full_run_job
test $(ls -A1q "$test_results/latest/test-results" | grep -v by-status | wc -l) == 2 || (echo "Unexpected or missing tests replayed" && exit 1)
ls -A1q "$test_results/latest/test-results" | grep -q client_noop || (echo "The client_noop test was not rerun or cleaned from previous run" && exit 1)
ls -A1q "$test_results/latest/test-results" | grep -q explicit_noop || (echo "The explicit_noop test was not rerun or cleaned from previous run" && exit 1)
$avocado_cmd setup=run nets=$test_slots only=tutorial1 replay=$full_run_job rerun_status=pass
test -d "$test_results"/latest/test-results || (echo "Passing tests were not replayed" && exit 1)

echo
echo "Testing a mix of shared pool and serial run"
ls -A1q /mnt/local/images/shared/vm1-* 2>/dev/null | grep -q . && (echo "Unexpected vm1 images in the shared pool found" && exit 1)
mv /mnt/local/images/swarm/vm1-* /mnt/local/images/shared/
$avocado_cmd setup=run only=tutorial1 nets=net0
test -d "$test_results"/latest/test-results || (echo "No serial tests found" && exit 1)
ls -A1q "$test_results/latest/test-results" | grep -q install && (echo "Unwanted install test found and shared pool wasn't reused" && exit 1)
ls -A1q "$test_results/latest/test-results" | grep -q tutorial1 || (echo "The tutorial1 test wasn't run serially" && exit 1)

echo
echo "Test coverage for manual tools of all main types"
$avocado_cmd setup=control nets=$test_slots vms=vm1,vm2 control_file=manual.control
container_array=($containers)
test $(ls -A1q "$test_results/latest/test-results" | grep -v by-status | wc -l) == $((${#container_array[@]}-1)) || (echo "Incorrect total of control file runs" && exit 1)
test $(ls -A1q "$test_results/latest/test-results" | grep manage.run | wc -l) == $((${#container_array[@]}-1)) || (echo "Incorrect number of control file runs" && exit 1)
$avocado_cmd setup=get nets=$test_slots vms=vm1,vm2 get_state_images=customize
test $(ls -A1q "$test_results/latest/test-results" | grep -v by-status | wc -l) == $((${#container_array[@]}*2-1)) || (echo "Incorrect number of total state retrieval tests" && exit 1)
test $(ls -A1q "$test_results/latest/test-results" | grep stateful.get.vms.vm1 | wc -l) == $((${#container_array[@]}-1)) || (echo "Incorrect number of vm1 state retrieval tests" && exit 1)
test $(ls -A1q "$test_results/latest/test-results" | grep stateful.get.vms.vm2 | wc -l) == ${#container_array[@]} || (echo "Incorrect number of vm2 state retrieval tests" && exit 1)
echo "Skipping update tool until fixed for now"
$avocado_cmd setup=update nets=$test_slots vms=vm1,vm2 from_state=customize to_state_vm1=connect remove_set=tutorial3
test $(ls -A1q "$test_results/latest/test-results" | grep -v by-status | wc -l) == 3 || (echo "Incorrect number of total tests during update" && exit 1)
test $(ls -A1q "$test_results/latest/test-results" | grep customize | wc -l) == 2 || (echo "Incorrect number of customize tests during update" && exit 1)
test $(ls -A1q "$test_results/latest/test-results" | grep connect.vms.vm1 | wc -l) == 1 || (echo "Incorrect number of connect tests during update" && exit 1)

echo
echo "Integration tests passed successfully"
