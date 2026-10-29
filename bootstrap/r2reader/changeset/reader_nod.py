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
# Then ruling 32's rename-and-rewrite search (changeset/run_search_nod.py,
# rw/run_search.py under stage 1's a.py) respelled the region: names and
# equivalent spellings chosen by compressed size, the same program (the
# functions above, now: fm be, wk ft, ld cb, v sz, cb u, be dd, ft fr; rb,
# sp, f, a, ax, w, b keep their names).
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
y=[(x,y,sum(r*r+r<x*x+y*y for r in range(7))&1<1)
 for y in range(-7,8)for x in range(-7,8)if x*x+y*y<57]
c=[(x,y)for y in range(-8,8)for x in range(-8,8)]
v=[(x,y)for x,y in c if x*x+y*y>56][:68]
fm=[(x,y,x+y&1)for y in range(-9,9)for x in range(-9,9)
 if{x,y}&{-9,8}]
def cb(c):
 s=open(c,'rb').read()
 i,p=[int(r)for r in s[:64].split()[1:3]]
 return i,p,s[len(s)-i*p:]
def u(s):
 z=[0]
 i,p=0,s[0]
 while i>=0:
  i=s.find(1-p,i)
  if i>0:p,z=1-p,z+[i]
 z+=[len(s)]
 return[(x+z[i+12]+z[i+13]-2,y)for i in range(1+s[0],len(z)-14,2)
  for x,y in[(z[i]+z[i+1],z[i+12]+z[i+13]-z[i]-z[i+1])]
  if 23<y and min(z[i]-z[i-1],z[i+14]-z[i+13])*96>=y and max(
  abs(12*(z[i+r+6]+z[i+r+7]-x)-(r+6)*y)for r in(-5,5,-4,4,-3,3,-2,2)
  )<=(3*y+144)//10]
def sp(s,x,y):
 return s[0]+(s[2][0]*x+s[3][0]*y)//17,s[1]+(s[2][1]*x+s[3][1]*y)//17
def ax(x,y,p,r,t):
 s=4096-(r*r>>13)
 z=[17*p*s>>16,17*p*r>>16]
 m=[-17*p*r>>16,17*p*s>>16]
 for i in range(t):z,m=m,[-z[0],-z[1]]
 return[x,y,z,m]
def sz(x,y):
 x,y=min(max(x,0),16*h-17),min(max(y,0),16*j-17)
 i,q,n=(y>>4)*h+(x>>4),x&15,y&15
 return((z[i]*(16-q)+z[i+1]*q)*(16-n)
  +(z[i+h]*(16-q)+z[i+h+1]*q)*n)//256
def dd(c):
 s=[]
 for i in range(j):
  for k,z in u(c[i*h:i*h+h]):
   x=k+2>>2
   if[s for s in s if 16*abs(s[1]-4*k)+16*abs(s[2]-16*i)<6*s[3]]:
    continue
   q,n=max(0,i-z//2-2),min(j,i+z//2+3)
   m,r,t=min([(abs(x-4*(i-q)),x,y)for x,y in u(c[q*h+x:n*h:h])]
    +[(z,0,0)])
   if z<6*m:continue
   x,a,p=4*k,4*(r+4*q),16*(z+t)//3
   if min(x,a)<p//2 or x>16*h-p//2-32 or a>16*j-p//2-32:continue
   g=sum(c[(a+(y*p>>4)+8>>4)*h+(x+(i*p>>4)+8>>4)]==k for i,y,k in y)
   if 4*g>=3*len(y):s+=[(g,x,a,p)]
 return s
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
   x=rb(s)
   if x:i+=[x]
  ou=[(sz(*sp(s,x,y)),1-2*(k^s[4]))for x,y,k in fm]
  g=sum(a for a,b in ou)//68
  if 5*sum(b*a for a,b in ou)>=3*sum(abs(a-g)for a,b in ou):
   o[q,a,b]=s
   t+=[[s[0]+y*s[2+x//2][0],s[1]+y*s[2+x//2][1],s[2],s[3],1-s[4],
    (q,a+y*(x>1),b+y*(x<2))]for x in range(4)for y in[1-2*(x&1)]]
 return i
def w(s):
 return sum(sz(*sp(s,x,y))*(1-2*k)for x,y,k in fm)
def rb(s):
 r,t=f(s)
 if sum(r[x,y]<t for x,y in c)>3:return a(r,t,c,32)
def fr(s,p):
 c=[(sp(s,x,y),1-2*(k^s[4]))for x,y,k in fm]
 m=n=0
 for y in(p>>5,p>>6,p>>7,p//256):
  k,k,m,n=max((sum(sz(x+s,a+r)*y for(x,a),y in c),-abs(s-m)-abs(r-n)
   ,s,r)for s in(m-y,m,m+y)for r in(n-y,n,n+y))
 return m,n
def b(c):
 s=2**32-1
 for t in c:
  s=s^t
  for x in range(8):s=s>>1^3988292384*(s&1)
 return s^2**32-1
def a(z,m,c,y):
 r=len(c)
 s=int(''.join('01'[m-z[i,y]+(z[i-1,y]+z[i+1,y]+z[i,y-1]+z[i,y+1]
  -4*z[i,y]>>1)>0]for i,y in c),2)
 for t in[0]+[1<<t for t in range(r*(y>20))]:
  x=s^t
  if b(e+(x>>y).to_bytes((r-y)//8,'big'))%2**y==x%2**y:
   return(x>>y).to_bytes((r-y)//8,'big')
def f(s):
 r={(x,y):sz(*sp(s,x,y))for y in range(-9,9)for x in range(-9,9)}
 z=sorted(r[x,y]for x,y,k in fm)
 return r,z[8]+z[59]>>1
def be():
 c=dd(z.translate(bytes(x<t for t in[min(z[::97])+max(z[::97])>>1]
  for x in range(256))))
 k,k,m,n=max((sum(abs(w(ax(x,y,p,r,t)))for k,x,y,p in c),-abs(r),r,t)
  for r in range(-640,641,64)for t in range(4))
 r=[]
 for k,x,y,p in c:
  t=ax(x,y,p,m,n)
  r+=[t+[int(w(t)<0),(len(r),0,0)]]
 s=e
 for t in r:s=s or a(*f(t),v,20)
 return(c[0][3]if c else 0,r),s or e
e,i,s,t=b'',0,{},'?'
while i<1:
 r=0
 try:
  r=input('file: ').strip()
  h,j,z=cb(r)
  m,e=be()
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
