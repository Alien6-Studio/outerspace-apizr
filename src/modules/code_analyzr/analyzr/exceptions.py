class UnsupportedKeywordError(Exception):
    """Raised when an unsupported Python keyword is detected."""

    def __init__(self, keyword, introduced_version, current_version):
        self.keyword = keyword
        self.introduced_version = introduced_version
        self.current_version = current_version
        message = (
            f"The keyword '{self.keyword}' was introduced in Python "
            f"{self.introduced_version[0]}.{self.introduced_version[1]} and might not be "
            f"recognized in your current version {self.current_version[0]}.{self.current_version[1]}."
        )
        super().__init__(message)
