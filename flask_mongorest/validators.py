import re
from flask.ext.mongorest.exceptions import ValidationError

"""
Derived from WTForms.  https://bitbucket.org/simplecodes/wtforms/src/270fbd8828cb/wtforms/validators.py
"""

class Length(object):
    """
    Validates the length of a string.

    :param min:
        The minimum required length of the string. If not provided, minimum
        length will not be checked.
    :param max:
        The maximum length of the string. If not provided, maximum length
        will not be checked.
    """
    def __init__(self, min=-1, max=-1, message=None):
        super(Length, self).__init__()
        assert min != -1 or max!=-1, 'At least one of `min` or `max` must be specified.'
        assert max == -1 or min <= max, '`min` cannot be more than `max`.'
        self.min = min
        self.max = max
        self.message = message

    def __call__(self, data):
        l = data and len(data) or 0
        if l < self.min or self.max != -1 and l > self.max:
            if not self.message:
                if self.max == -1:
                    self.message = 'Field must be at least %(min)d character(s) long.'
                elif self.min == -1:
                    self.message = 'Field cannot be longer than %(max)d character(s).'
                else:
                    self.message = 'Field must be between %(min)d and %(max)d characters long.'

            raise ValidationError(self.message % dict(min=self.min, max=self.max))

class Required(object):
    """
    Validates that the field contains data. This validator will stop the
    validation chain on error.
    """
    def __init__(self, message='Field is required.'):
        self.message = message

    def __call__(self, data):
        if not data or isinstance(data, basestring) and not data.strip():
            raise ValidationError(self.message)

class Optional(object):
    """
    Allows empty input and stops the validation chain from continuing.
    """
    def __call__(self, data):
        pass

class Regexp(object):
    """
    Validates the field against a user provided regexp.

    :param regex:
        The regular expression string to use. Can also be a compiled regular
        expression pattern.
    :param flags:
        The regexp flags to use, for example re.IGNORECASE. Ignored if
        `regex` is not a string.
    """
    def __init__(self, regex, flags=0, message='Invalid data.'):
        if isinstance(regex, basestring):
            regex = re.compile(regex, flags)
        self.regex = regex
        self.message = message

    def __call__(self, data):
        if not self.regex.match(data or u''):
            raise ValidationError(self.message)

class Email(Regexp):
    """
    Validates an email address. Note that this uses a very primitive regular
    expression and should only be used in instances where you later verify by
    other means, such as email activation or lookups.
    """
    def __init__(self, message='Invalid email address.'):
        super(Email, self).__init__(r'^.+@[^.].*\.[a-z]{2,10}$', re.IGNORECASE, message)

    def __call__(self, data):
        super(Email, self).__call__(data)

length = Length
required = Required
optional = Optional
regexp = Regexp
email = Email

