class BOT_CONSTANTS:
    OPENAI_API_KEY = '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'
    OPENAI_INSTRUCTIONS = 'Always answer in the same language in which you were asked a question.'
    OPENAI_FILE_ID = 'file-b0w5vx0LtqwA3uv3jDhwSPOM'
    OPENAI_ASSISTANT_ID = 'asst_8gBOLO4RVasmZzsrIxz9n0pv'
    OPENAI_ERROR_MSG = 'The AI is not responsive. You may need to re-enter your request at a later time.'

    TG_BOT_TOKEN = '6881817627:AAEgL44OZ_dklg7YmP872LUkDg-okKd3j8U'
    TG_BOT_GREETING = 'I am an mRNA Expert Bot, ready to answer your questions regarding mRNA vaccines.'
    TG_MAX_THREADS = 10000
    TG_MAX_MESSAGES = 10000
    TG_BOT_CALLSIGNS = [
        "mRNAExpert",
        "bohouš",
        "bot",
    ]
    VERBOSE = True
    
    DOCUMENT_TYPES = [
        {
            'name': 'academic_lecture',
            'display_name': 'Academic Lecture',
            'description': 'Create an academic lecture',
            'class_path': 'documentdrivers.academic.LectureDriver',
        },
        {
            'name': 'poetry',
            'display_name': 'Poetry',
            'description': 'Compose a poem',
            'class_path': 'documentdrivers.poetry.PoetryDriver', # not implemented
        },
        # Add more types with class_path and method
    ]

    # CONCURRENCY: max. number of concurrent document generation tasks
    # 0 = unlimited concurrent tasks
    # 1 = max 1 task at a time 
    # 2 = max 2 tasks at a time etc.
    CONCURRENCY = 1
    
    # logging levels:
    # 'CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG' and 'NOTSET'
    LOGGING_LEVEL = 'ERROR'
    

    # define the telegram bot commands here
    # __init__ in TelegramBot class will automatically create the event listeners.
    # You then just need to implement the event handler methods.
    # The fields 'short_description' and 'help_text' are translated, hence 
    # don't forget to add these to the StringLiteral.translations dictionary in locales.py.
    TG_BOT_COMMANDS = [
        {
            'command': 'create',
            'short_description': 'have a document of your choice created', # don't forget to add the short_description to locales.py translations
            'help_text': 'Enter \'/create\' in the Telegram command line and post it to activate the document generator.', # translations!!
            'event_handler': 'botcommand_create_handler_async',
        },
        {
            'command': 'help',
            'short_description': 'lists available bot commands', # don't forget to add the short_description to locales.py translations
            'help_text': 'Enter \'/help\' in the Telegram command line and post it to display the help information.', # translations!!
            'event_handler': 'botcommand_help_handler_async',
        },
        # Add more commands
    ]