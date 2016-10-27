import logging


class LogSender():
    """
    main_logger = LogSender(log_config={'log_location': '/tmp/test.log', 'log_driver': 'file'})
    main_logger.send_log('test')
    """
    def __init__(self, log_config):
        self.log_config = log_config

        if self.log_config['log_driver'] == 'file':
            logging.basicConfig(filename=self.log_config['log_location'], filemode='w', level=logging.DEBUG)

    def send_log(self, log_message='', log_level='error'):
        logging.error(log_message)
        return
