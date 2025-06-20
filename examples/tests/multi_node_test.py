"""
Please put the configuration file multi_node_test.cfg into $tests/cfg/ directory.
"""

def run(test, params, env):
    for node in test.nodes:
        test.log.info("========Start test on %s========", node.name)
        node.proxy.unittest.hello.say()
        node.proxy.unittest.testcase.vm.boot_up()
        test.log.info("========End test========")
