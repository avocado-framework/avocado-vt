from transitions import Machine


def register_pool_state_machine(instance):
    states = ['dead', 'ready', 'running']
    transitions = [
        {'trigger': 'start_pool',
         'source': ['dead', 'ready'],
         'dest': 'running',
         'after': 'start'},
        {'trigger': 'stop_pool',
         'source': 'running',
         'dest': 'ready',
         'after': 'stop'},
        {'trigger': 'destroy_pool',
         'source': ['stop', 'ready'],
         'dest': 'dead',
         'after': 'destroy'}
    ]
    machine = Machine(
        model=instance,
        states=states,
        transitions=transitions,
        initial="dead")
    return machine
