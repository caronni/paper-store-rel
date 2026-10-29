# reader_lite_v1.py -- the typed stage-2 reader for R2-FORMAT v1 (2026-10-20,
# the set pass: "Simplify the reader! good enough recovery, not perfect").
# diet/v1/d06_panel21.py hand-minified (m07; by hand m08, m10-m12, m14;
# names by diet/w4_names.py at m09); the record: diet/LADDER-2026-10-20.md.
# The ALTERNATIVE to the 2026-10-22 change set (changeset/apply_nod.py,
# measured in changeset/RESULTS-2026-10-22.md section 12; the print of
# record's text is git b544669e): the stage names of ruling 34 (the primer
# read from b.py, the output written as c.py); the quarter turn folded into
# ax, the ring by the parity of the rounded radius and the block read
# merged into the first test of the walk; the frame check on the block
# centre; the prompt 'file: '; the 0/1 text grid no longer read (the
# Plate's one-liner, r2reader/grid_to_pgm.py, writes the PGM); a score tie
# in ft broken toward the nearest offset, in fm toward the smallest
# rotation.  The walk is NOT CRC-gated: it keeps the record's timing test.
# Only the region between the READER markers is typed, minus the shared
# block (the loader's d, here so the file runs on its own).  Run: python3
# reader_nod.py beside b.py (the primer), one P5 PGM frame per line, an
# empty line or the end of input stops; a file that cannot be read is
# reported and skipped.
# BEGIN READER
#--- shared with the loader (not typed) ---
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
#--- end shared ---
def b(c):
 s=2**32-1
 for y in c:
  s^=y
  for j in range(8):s=s>>1^3988292384*(s&1)
 return s^2**32-1
y=[(x,y,sum(k*k+k<x*x+y*y for k in range(7))%2<1)
 for y in range(-7,8)for x in range(-7,8)if x*x+y*y<57]
m=[(x,y)for y in range(-8,8)for x in range(-8,8)]
hd=[(x,y)for x,y in m if x*x+y*y>56][:68]
fr=[(x,y,(x+y)%2)for y in range(-9,9)for x in range(-9,9)
 if{x,y}&{-9,8}]
def ld(c):
 s=open(c,'rb').read()
 q,p=[int(s)for s in s[:64].split()[1:3]]
 return q,p,s[len(s)-q*p:]
def v(x,y):
 x=min(max(x,0),16*h-17)
 y=min(max(y,0),16*j-17)
 i,q,p=(y>>4)*h+(x>>4),x&15,y&15
 return((z[i]*(16-q)+z[i+1]*q)*(16-p)
  +(z[i+h]*(16-q)+z[i+h+1]*q)*p)>>8
def cb(s):
 z,n,p=[0],0,s[0]
 while n>=0:
  n=s.find(1-p,n)
  if n>0:z,p=z+[n],1-p
 z+=[len(s)]
 return[(r+z[i+12]+z[i+13]-2,t)for i in range(1+s[0],len(z)-14,2)
  for r,t in[(z[i]+z[i+1],z[i+12]+z[i+13]-z[i]-z[i+1])]
  if t>23 and 96*min(z[i]-z[i-1],z[i+14]-z[i+13])>=t and max(
  abs(12*(z[i+y+6]+z[i+y+7]-r)-(y+6)*t)for y in(-5,5,-4,4,-3,3,-2,2)
  )<=(3*t+144)//10]
def be(c):
 s=[]
 for i in range(j):
  for k,z in cb(c[i*h:i*h+h]):
   x=k+2>>2
   if[s for s in s if 16*abs(s[1]-4*k)+16*abs(s[2]-16*i)<6*s[3]]:
    continue
   q,a=max(0,i-z//2-2),min(j,i+z//2+3)
   m,r,t=min([(abs(r-4*(i-q)),r,t)for r,t in cb(c[q*h+x:a*h:h])]
    +[(z,0,0)])
   if 6*m>z:continue
   x,n,p=4*k,4*(r+4*q),16*(z+t)//3
   if min(x,n)<p//2 or x>16*h-p//2-32 or n>16*j-p//2-32:continue
   g=sum(c[(n+(y*p>>4)+8>>4)*h+(x+(r*p>>4)+8>>4)]==k for r,y,k in y)
   if 4*g>=3*len(y):s+=[(g,x,n,p)]
 return s
def sp(s,x,y):
 return s[0]+(s[2][0]*x+s[3][0]*y)//17,s[1]+(s[2][1]*x+s[3][1]*y)//17
def ft(s,p):
 c=[(sp(s,x,y),1-2*(k^s[4]))for x,y,k in fr]
 m=n=0
 for y in(p//32,p//64,p//128,p//256):
  k,k,m,n=max((sum(v(x+r,y+q)*t for(x,y),t in c),-abs(r-m)-abs(q-n)
   ,r,q)for r in(m-y,m,m+y)for q in(n-y,n,n+y))
 return m,n
def f(s):
 c={(x,y):v(*sp(s,x,y))for y in range(-9,9)for x in range(-9,9)}
 z=sorted(c[x,y]for x,y,k in fr)
 return c,(z[8]+z[59])//2
def a(z,x,y,p):
 m=len(y)
 r=int(''.join('01'[x-z[i,k]+(z[i-1,k]+z[i+1,k]+z[i,k-1]+z[i,k+1]
  -4*z[i,k]>>1)>0]for i,k in y),2)
 for t in[0]+[1<<t for t in range(m*(p>20))]:
  n=r^t
  if b(e+(n>>p).to_bytes((m-p)//8,'big'))%2**p==n%2**p:
   return(n>>p).to_bytes((m-p)//8,'big')
def rb(s):
 r,t=f(s)
 if sum(r[x,y]<t for x,y in m)>3:return a(r,t,m,32)
def wk(p,t):
 w,f,i,c={},{},[],5*p>>4
 for s in t:
  x,y=s[0]//c,s[1]//c
  if(x,y)in w:continue
  w[x,y]=1
  if min(s[0],s[1],16*h-32-s[0],16*j-32-s[1])<5*p>>3:continue
  q,a,b=s[5]
  if a or b:
   m,n=ft(s,p)
   s[0],s[1]=s[0]+m,s[1]+n
   for k,z in((2,b),(3,a)):
    u=(z>0)-(z<0)
    g=f.get((q,a-u*(k>2),b-u*(k<3)))
    if g and u:s[k]=[u*(s[0]-g[0]),u*(s[1]-g[1])]
   x=rb(s)
   if x:i+=[x]
  r=[(v(*sp(s,x,y)),1-2*(k^s[4]))for x,y,k in fr]
  g=sum(a for a,b in r)//68
  if 5*sum(a*b for a,b in r)>=3*sum(abs(a-g)for a,b in r):
   f[q,a,b]=s
   t+=[[s[0]+t*s[2+x//2][0],s[1]+t*s[2+x//2][1],s[2],s[3],1-s[4],
    (q,a+t*(x>1),b+t*(x<2))]for x in range(4)for t in[1-2*(x%2)]]
 return i
def ax(x,y,p,r,t):
 s=4096-r*r//8192
 a,b=[17*p*s>>16,17*p*r>>16],[-17*p*r>>16,17*p*s>>16]
 for i in range(t):a,b=b,[-a[0],-a[1]]
 return[x,y,a,b]
def w(s):
 return sum(v(*sp(s,x,y))*(1-2*k)for x,y,k in fr)
def fm():
 c=be(z.translate(bytes(x<t for t in[(min(z[::97])+max(z[::97]))//2]
  for x in range(256))))
 k,k,m,n=max((sum(abs(w(ax(x,y,p,r,t)))for k,x,y,p in c),-abs(r),r,t)
  for r in range(-640,641,64)for t in range(4))
 r=[]
 for k,x,y,p in c:
  s=ax(x,y,p,m,n)
  r+=[s+[int(w(s)<0),(len(r),0,0)]]
 t=e
 for s in r:t=t or a(*f(s),hd,20)
 return(c[0][3]if c else 0,r),t or e
c,e,i,n={},b'',0,'?'
while i<1:
 r=0
 try:
  r=input('file: ').strip()
  h,j,z=ld(r)
  o,e=fm()
  g='%d bullseyes'%len(o[1])
  p=wk(*o)if e else[]
 except:
  if not r:break
  g,p='cannot read',[]
 for x in p:c[int.from_bytes(x[:2],'big')]=x[2:]
 if e:
  sz=int.from_bytes(e[:2],'big')
  n=(sz+25)//26
  if sum(i in c for i in range(n))==n:
   dd=b''.join(c[i]for i in range(n))[:sz]
   i=b(dd)==int.from_bytes(e[2:],'big')
 print(r+':',g+',',len(p),'blocks accepted, chunks',len(c),'/',n,
  ['more','done'][i])
if i:
 ou=d(int.from_bytes(dd,'big'),N2,open('b.py','rb').read())
 assert b(ou)==B2
 open('c.py','wb').write(ou)
# END READER
