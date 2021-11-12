import logging
import os
import sys
import time

import service_manager

basedir = os.path.dirname(__file__)
logs_dir = os.path.join(basedir, 'logs')

server_host = sys.argv[1]
server_port = sys.argv[2]


if __name__ == '__main__':
    os.makedirs(logs_dir, 0o777, True)
    timestamp = time.strftime("%Y-%b-%d-%H:%M:%S")
    logfile = os.path.join(logs_dir, "server_daemon_%s.log" % timestamp)
    fmt = '%(asctime)s [%(levelname)-5.5s] - %(message)s'
    logging.basicConfig(level=logging.DEBUG, format=fmt,
                        handlers=[logging.FileHandler(logfile),
                                  logging.StreamHandler()]
                        )

    target = os.path.join(logs_dir, "latest")
    if os.path.exists(target):
        os.unlink(target)
    os.symlink(logfile, target)

    logging.info("Listening on port %s.", server_port)
    services = service_manager.init_services()

    try:
        addr = (server_host, int(server_port))
        server = service_manager.RPCServer(addr)
        server.register_services(services)
        server.serve_forever()
    except KeyboardInterrupt:
        logging.warn("Keyboard interrupt received, exiting.")
        sys.exit(0)
    except Exception as e:
        logging.error(e, exc_info=True)
        sys.exit(-1)
