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
            'method': 'create_lecture'
        },
        {
            'name': 'poetry',
            'display_name': 'Poetry',
            'description': 'Compose a poem',
            'class_path': 'documentdrivers.poetry.PoetryDriver',
            'method': 'create_poem'
        },
        # Add more types with class_path and method
    ]
