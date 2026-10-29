def k(t):
 b=f
 for i in t:
  b^=i
  for j in range(8):b=b>>1^3988292384*(b&1)
 return f-b
def e(c):t=[i for i in range(len(c))if c[i]*16>max(c)];return t[0],t[-1]
def u(v,p):
 (c,a),(b,r),(s,w),(k,j)=v
 d,e=c-b+k-s,a-r+j-w
 m,g,i,n=b-k,s-k,r-j,w-j
 x=m*n-g*i
 u,h=d*n-e*g,m*e-i*d
 return(b-c)*x+u*b,(s-c)*x+h*s,c*x,(r-a)*x+u*r,(w-a)*x+h*w,a*x,u,h,x,*p
def v(s,n,h):
 a,b=(2*n+1)*s[10],(2*h+1)*s[9]
 t=s[6]*a+s[7]*b+s[8]*s[9]*s[10]
 return[(s[i]*a+s[i+1]*b+s[i+2]*s[9]*s[10])//t for i in(0,3)]
def r(b,c,a,r):return[(x,y)for y in range(c-a*r,c+a*r+1,r)for x in range(b-a*r,b+a*r+1,r)]
def de(m,x,s):
 w=[[0]*(17*z+1)for r in range(17*bh+1)]
 p={}
 for i in range(bh)[::-1]:
  for j in range(z)[::-1]:
   q={(p,r):v(x,p,r)for r in range(17*i,17*i+18)for p in range(17*j,17*j+18)}
   g=[p for p in q if p[0]%17*(p[1]%17)<1]
   b=lambda p,s:m((q[p][0]+s[0],q[p][1]+s[1]))
   c,n=p.get((i,j+1))or p.get((i+1,j))or(0,0),[1,8][not p]
   for d in(2,4,8,16):f,c=max((sum(b(p,c)*(1-(p[0]+p[1])%2*2)for p in g),c)for c in r(*c,n,s//d));n=1
   p[i,j]=c
   a={p:b(p,c)for p in q}
   t=sum(a[p]for p in g)//68
   for(k,y)in q:w[y][k]=t-a[k,y],k%17 and y%17 and a[k-1,y]+a[k+1,y]+a[k,y-1]+a[k,y+1]-4*a[k,y]
 return w
def m(a,n,h):
 q=a[::97];t=sum(q)//len(q)
 b=a.translate(bytes(x<t for x in range(256)))
 d,r=[0]*n,[0]*h
 for k in range(n*h-n-1):d[k%n]+=b[k]!=b[k+n];r[k//n]+=b[k]!=b[k+1]
 (v,w),(c,g)=e(d),e(r)
 s=[(-1<<40,0,0)]*4
 for y in range(c,g+1):
  f=b.find(1,y*n+v,y*n+w+1)
  p=b.rfind(1,y*n+v,y*n+w+1)
  for k in range(4*(f>=0)):x,i,j=[f,p][k&1]-y*n,k&1,k>>1;s[k]=max(s[k],((2*i-1)*x+(2*j-1)*y,x,y))
 def m(s):
  k=min(max(s[0],0),16*n-17)
  f=min(max(s[1],0),16*h-17)
  i,b,y=(f>>4)*n+(k>>4),k&15,f&15
  return(a[i]*(16-b)+a[i+1]*b)*(16-y)+(a[i+n]*(16-b)+a[i+n+1]*b)*y>>8
 g=[[16*x for x in s[k][1:3]]for k in range(4)]
 return de(m,u(g,(34*z+2,34*bh+2)),(s[1][1]-s[0][1]+s[3][1]-s[2][1])*8//(17*z+1))
def d(b):
 for i in(8,4,0):
  s=[p[0]+(p[1]*i>>3)for p in b]
  q=sorted(range(256),key=lambda p:abs(s[p]))[:6]
  for x in range(64+256*(i==0)):
   p=[(s[k]>0)^(k==x-64)^(x<64 and k in q and x>>q.index(k)&1)for k in range(256)]
   w=bytes(sum(p[8*k+j]<<7-j for j in range(8))for k in range(32))
   if k(w[:28])==int.from_bytes(w[28:],'big'):return w
def x(b):
 p=open(b,'rb').read()
 if p[0]!=80:return[[((x==49)-(x==48),0)for x in p]for p in p.split()]
 s=p[:30].split();n,h=int(s[1]),int(s[2])
 return m(p[-n*h:],n,h)
f,b,y,z,bh=2**32-1,{},0,21,30
while not y:
 p=input('r2 page, pgm or grid text (empty line: stop): ')
 if not p:break
 c,a=x(p),{}
 for i in range(z*bh):
  p=d([c[i//z*17+1+k//16][i%z*17+1+k%16]for k in range(256)])
  if p:a[i]=b[p[0]<<8|p[1]]=p[2:28]
 s=b.get(0,bytes(26))
 n=int.from_bytes(s[4:8],'big')
 t=(n+25)//26+1
 q=[i for i in range(t)if i not in b]
 g=b''.join(b.get(i,bytes(26))for i in range(1,t))[:n]
 if not q:y=k(g)==int.from_bytes(s[8:12],'big')
 open('r2.bin','wb').write(g*y)
 print('blocks',len(a),'/',z*bh-4,'chunks',t-len(q),'/',t,['missing','ok'][y],q)
