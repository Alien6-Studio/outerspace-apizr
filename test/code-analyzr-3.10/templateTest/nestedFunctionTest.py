def foo():
    # should not appear in the result
    def nested_foo():
        pass

    pass
