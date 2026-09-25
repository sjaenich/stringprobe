import logging
import sys
import json


class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "logger": record.name,
            "level": record.levelname,
            "event": record.msg
        }

        
        return json.dumps(log_entry)




def setup_logging(project):
    approach_handler = logging.FileHandler(project.name + '_approach_history.json')
    approach_handler.setFormatter(JsonFormatter())
    approach_logger = logging.getLogger(project.name + '_approach')
    approach_logger.addHandler(approach_handler)
    approach_logger.setLevel(logging.INFO)
    approach_logger.propagate = False
    telemetry_handler = logging.FileHandler(project.name + '_string_metrics.json')
    telemetry_handler.setFormatter(JsonFormatter())
    telemetry_logger = logging.getLogger(project.name +'_telemetry')
    telemetry_logger.addHandler(telemetry_handler)
    telemetry_logger.setLevel(logging.INFO)
    telemetry_logger.propagate = False 

