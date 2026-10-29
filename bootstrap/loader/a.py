a=open('a.py').read().strip().encode()
def d(x,n,r):
 z=[256**q-1 for q in(0,1,2,3,4,6,8,12,16)]
 m,t,h=len(r),{},0
 for i in range(m+n):
  u=1
  for j in range(8):
   g=[t.setdefault((h&q,u),[0,0])for q in z]
   p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
   s=sum(p)
   if i<m:y=r[i]>>7-j&1
   else:o=x%s;y=o>=p[0];x=x//s*p[y]+o-p[0]*y
   for c in g:c[y],c[1-y]=c[y]+1,min(c[1-y],c[1-y]//4+2)
   u=2*u+y
  h=h<<8|u&255
 return h.to_bytes(m+n,'big')[m:]
q,n,v='0123456789abcdefghjkmnpqrstvwxyz',1,0
def k(n,t):
 for c in t:n=(n+c)*1000003
 return''.join(q[n>>s&31]for s in(15,10,5,0))
for(i,t)in enumerate(a.splitlines(),1):print(i,k(i,t))
while n<49:
 t=input([n]).replace(' ','')
 if k(n,t[:-4].encode())==t[-4:]:
  n+=1
  for c in t[:-4]:v=v*32+q.index(c)
r=d(v,4564,a)
assert k(0,r)=='y98y'
open('r.py','wb').write(a[39:608]+r)
