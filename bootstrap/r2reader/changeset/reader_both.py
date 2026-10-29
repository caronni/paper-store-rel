# reader_lite_v1.py -- the typed stage-2 reader for R2-FORMAT v1 (2026-10-20,
# the set pass: "Simplify the reader! good enough recovery, not perfect").
# diet/v1/d06_panel21.py hand-minified (m07; by hand m08, m10-m12, m14;
# names by diet/w4_names.py at m09); the record: diet/LADDER-2026-10-20.md.
# The UNION gate (changeset/apply_both.py on changeset/apply_nod.py's text,
# measured in changeset/RESULTS-2026-10-22.md section 13; the print of
# record's text is git b544669e): the stage names of ruling 34 (the primer
# read from b.py, the output written as c.py); the quarter turn folded into
# ax, the ring by the parity of the rounded radius and the block read
# merged into the first test of the walk; the frame check on the block
# centre; the prompt 'file: '; the 0/1 text grid no longer read (the
# Plate's one-liner, r2reader/grid_to_pgm.py, writes the PGM); a score tie
# in ft broken toward the nearest offset, in fm toward the smallest
# rotation.  The walk passes a seed, a block whose CRC checks, a white
# block, or a block whose timing test passes (the record's test kept).
# Then ruling 32's rename-and-rewrite search (changeset/run_search_both.py,
# rw/run_search.py under stage 1's a.py) respelled the region: names and
# equivalent spellings chosen by compressed size, the same program (the
# functions above, now: fm ld, wk ft, rb be, ld dd, v sz, cb u, be v, ft fr;
# sp, f, a, ax, w, b keep their names).
# Only the region between the READER markers is typed, minus the shared
# block (the loader's d, here so the file runs on its own).  Run: python3
# reader_both.py beside b.py (the primer), one P5 PGM frame per line, an
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
def ld():
 c=v(z.translate(bytes(x<t for t in[(min(z[::97])+max(z[::97]))//2]
  for x in range(256))))
 k,k,m,n=max((sum(abs(w(ax(x,y,p,r,t)))for k,x,y,p in c),-abs(r),r,t)
  for r in range(-640,641,64)for t in range(4))
 r=[]
 for k,x,y,p in c:
  s=ax(x,y,p,m,n)
  r+=[s+[int(w(s)<0),(len(r),0,0)]]
 b=e
 for s in r:b=b or a(*f(s),cb,20)
 return(c[0][3]if c else 0,r),b or e
def b(c):
 s=2**32-1
 for t in c:
  s=s^t
  for r in range(8):s=s>>1^3988292384*(s&1)
 return s^2**32-1
def ax(x,y,p,r,t):
 s=4096-(r*r>>13)
 g=[17*p*s>>16,17*p*r>>16]
 b=[-17*p*r>>16,17*p*s>>16]
 for i in range(t):g,b=b,[-g[0],-g[1]]
 return[x,y,g,b]
y=[(x,y,sum(r*r+r<x*x+y*y for r in range(7))&1<1)
 for y in range(-7,8)for x in range(-7,8)if x*x+y*y<57]
c=[(x,y)for y in range(-8,8)for x in range(-8,8)]
cb=[(x,y)for x,y in c if x*x+y*y>56][:68]
rb=[(x,y,x+y&1)for y in range(-9,9)for x in range(-9,9)
 if{x,y}&{-9,8}]
def dd(c):
 s=open(c,'rb').read()
 i,p=[int(r)for r in s[:64].split()[1:3]]
 return i,p,s[len(s)-i*p:]
def fr(s,p):
 c=[(sp(s,x,y),1-2*(k^s[4]))for x,y,k in rb]
 m=n=0
 for y in(p>>5,p>>6,p>>7,p//256):
  k,k,m,n=max((sum(sz(x+s,b+r)*y for(x,b),y in c),-abs(s-m)-abs(r-n)
   ,s,r)for s in(m-y,m,m+y)for r in(n-y,n,n+y))
 return m,n
def w(s):
 return sum(sz(*sp(s,x,y))*(1-2*k)for x,y,k in rb)
def sz(x,y):
 x,y=min(max(x,0),16*h-17),min(max(y,0),16*j-17)
 q,i,p=x&15,(y>>4)*h+(x>>4),y&15
 return((z[i]*(16-q)+z[i+1]*q)*(16-p)
  +(z[i+h]*(16-q)+z[i+h+1]*q)*p)//256
def v(c):
 s=[]
 for i in range(j):
  for k,z in u(c[i*h:i*h+h]):
   x=k+2>>2
   if[s for s in s if abs(s[1]-4*k)*16+16*abs(s[2]-16*i)<6*s[3]]:
    continue
   q,n=max(0,i-z//2-2),min(j,i+z//2+3)
   m,r,t=min([(abs(x-4*(i-q)),x,y)for x,y in u(c[q*h+x:n*h:h])]
    +[(z,0,0)])
   if z<6*m:continue
   x,b,p=4*k,4*(r+4*q),16*(z+t)//3
   if min(x,b)<p//2 or x>16*h-p//2-32 or b>16*j-p//2-32:continue
   g=sum(c[(b+(y*p>>4)+8>>4)*h+(x+(i*p>>4)+8>>4)]==k for i,y,k in y)
   if len(y)*3<=4*g:s+=[(g,x,b,p)]
 return s
def u(s):
 z=[0]
 x,y=0,s[0]
 while x>=0:
  x=s.find(1-y,x)
  if x>0:y,z=1-y,z+[x]
 z+=[len(s)]
 return[(x+z[i+12]+z[i+13]-2,y)for i in range(1+s[0],len(z)-14,2)
  for x,y in[(z[i]+z[i+1],z[i+12]+z[i+13]-z[i]-z[i+1])]
  if y>23 and min(z[i]-z[i-1],z[i+14]-z[i+13])*96>=y and max(
  abs((z[i+h+6]+z[i+h+7]-x)*12-y*(h+6))for h in(-5,5,-4,4,-3,3,-2,2)
  )<=(y*3+144)//10]
def ft(p,t):
 r={}
 o={}
 i=[]
 c=5*p>>4
 for s in t:
  x,y=s[0]//c,s[1]//c
  if(x,y)in r:continue
  r[x,y]=1
  if min(s[0],s[1],16*h-32-s[0],16*j-32-s[1])<5*p>>3:continue
  q,a,b=s[5]
  if a or b:
   m,n=fr(s,p)
   s[0],s[1]=s[0]+m,s[1]+n
   for k,z in((2,b),(3,a)):
    u=(z>0)-(z<0)
    g=o.get((q,a-u*(k>2),b-u*(k<3)))
    if g and u:s[k]=[u*(s[0]-g[0]),u*(s[1]-g[1])]
   x=be(s)
   if x:i+=[x]
  ou=[(sz(*sp(s,x,y)),1-2*(k^s[4]))for x,y,k in rb]
  g=sum(a for a,b in ou)//68
  if x!=None or sum(abs(a-g)for a,b in ou)*3<=5*sum(b*a for a,b in ou):
   o[q,a,b]=s
   t+=[[s[0]+y*s[2+x//2][0],s[1]+y*s[2+x//2][1],s[2],s[3],1-s[4],
    (q,a+y*(x>1),b+y*(x<2))]for x in range(4)for y in[1-2*(x&1)]]
 return i
def f(s):
 r={(x,y):sz(*sp(s,x,y))for y in range(-9,9)for x in range(-9,9)}
 z=sorted(r[x,y]for x,y,k in rb)
 return r,z[8]+z[59]>>1
def a(z,x,y,p):
 r=len(y)
 s=int(''.join('01'[x-z[i,k]+(z[i-1,k]+z[i+1,k]+z[i,k-1]+z[i,k+1]
  -4*z[i,k]>>1)>0]for i,k in y),2)
 for t in[0]+[1<<t for t in range(r*(p>20))]:
  g=s^t
  if g%2**p==b(e+(g>>p).to_bytes((r-p)//8,'big'))%2**p:
   return(g>>p).to_bytes((r-p)//8,'big')
def sp(s,x,y):
 return s[0]+(s[2][0]*x+s[3][0]*y)//17,s[1]+(s[2][1]*x+s[3][1]*y)//17
def be(s):
 r,t=f(s)
 return a(r,t,c,32)if sum(r[x,y]<t for x,y in c)>3 else b''
e,i,s,t=b'',0,{},'?'
while i<1:
 r=0
 try:
  r=input('file: ').strip()
  h,j,z=dd(r)
  m,e=ld()
  n='%d bullseyes'%len(m[1])
  p=ft(*m)if e else[]
 except:
  if not r:break
  n='cannot read'
  p=[]
 for x in p:s[int.from_bytes(x[:2],'big')]=x[2:]
 if e:
  g=int.from_bytes(e[:2],'big')
  t=(g+25)//26
  if t==sum(x in s for x in range(t)):
   o=b''.join(s[x]for x in range(t))[:g]
   i=b(o)==int.from_bytes(e[2:],'big')
 print(r+':',n+',',len(p),'blocks accepted, chunks',len(s),'/',t,
  ['more','done'][i])
if i:
 ou=d(int.from_bytes(o,'big'),N2,open('b.py','rb').read())
 assert b(ou)==B2
 open('c.py','wb').write(ou)
# END READER
