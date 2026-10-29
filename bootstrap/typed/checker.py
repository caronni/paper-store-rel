# The hand-typed checker (TYPED-STREAM v0). Type ONLY the 12 lines between
# the markers, in an empty folder; run it there (python3 checker.py) and
# again after any crash -- it resumes from s.txt. It prints OK n (type line
# n next) or BAD n (retype line n). RUN writes a.py and runs it.
# BEGIN CHECKER
A = '0123456789abcdefghijklmnopqrstuv'
l = n = open('s.txt', 'a').write('')
while l != 'RUN':
    L = open('s.txt').read().split('\n')
    print(['BAD', 'OK'][len(L) > n], len(L))
    l, n = input(), len(L)
    c = n * 1000003 + sum(i * ord(x) for i, x in enumerate(l[:-3], 1))
    if l[-3:] == A[c >> 10 & 31] + A[c >> 5 & 31] + A[c & 31]:
        open('s.txt', 'a').write(l[:-3] + '\n')
t = ''.join(L).split('###')
open('a.py', 'w').write(t[0].translate({126: '\n', 64: '    '}))
exec(open('a.py').read())
# END CHECKER
