# document_driver_base.py
#
# Interface class for document drivers.
# Each document driver must inherit this class
# and implement the execute() and is_complete() methods.
# This is required because document driver modules are imported 
# and instantiated dynamically in telegrambot.echo()

class DocumentDriverBase:
    async def execute(self, update, context, message_text):
        raise NotImplementedError("Subclasses must implement this method")
    
    def is_complete(self):
        raise NotImplementedError("Subclasses must implement this method")
