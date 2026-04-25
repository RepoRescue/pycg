def alpha():
    return beta() + 1


def beta():
    return 42


class Foo:
    def method(self):
        return alpha()


def main():
    f = Foo()
    return f.method()


if __name__ == "__main__":
    main()
