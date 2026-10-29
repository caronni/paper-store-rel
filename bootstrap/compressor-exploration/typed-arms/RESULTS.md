# v2-lab-typed: cm2 arms at the typed rung (all MEASURED here, 2026-10-20)

Currency: total typed = 826 + delta + glyphs + 4*ceil(glyphs/60). Baseline 3,894 (1,797.125 B, 2,876 glyphs, 48 lines); mono 10,599.0 B; T3 (T3_32k.txt, primer a.py) 7,216.25 B exact / 7,215.0 ideal.
Model = the arm's own d() text instrumented (coder lines -> logging), so encoder == decoder; primer = the MODIFIED a.py (and modified r.py slice for mono). exact = x.bit_length()/8 from the exact rANS; rt = round trip through the unmodified arm d().

| arm | delta | typed B ideal | typed B exact | total typed | mono B | T3 B | rt typed/mono |
|---|---|---|---|---|---|---|---|
| primer_d_last | +0 | 1796.7 | 1796.625 | 3893 | 10599.0 | 7216.5 | True/True |
| base | +0 | 1797.2 | 1797.125 | 3894 | 10599.0 | 7216.2 | True/True |
| combo_dlast+wq-q//4 | +5 | 1795.0 | 1795.0 | 3895 | 10575.9 | 7270.8 | True/True |
| w_q-q//4 | +5 | 1795.5 | 1795.5 | 3896 | 10575.8 | 7270.5 | True/True |
| primer_d_last+shiftall1 | +2 | 1798.5 |  | (3898) | 10620.1 | 7221.5 | None/None |
| combo_dlast+wq-(q>6) | +6 | 1795.9 | 1795.875 | 3898 | 10593.8 | 7212.0 | True/True |
| shiftall_1 | +2 | 1799.1 |  | (3899) | 10620.0 | 7221.2 | None/None |
| w_q-(q>6) | +6 | 1796.5 | 1796.5 | 3899 | 10593.8 | 7211.8 | True/True |
| boost_above_0 | +6 | 1798.0 |  | (3901) | 10597.8 | 7215.0 | None/None |
| wtop_q>7 | +6 | 1798.4 |  | (3902) | 10600.2 | 7227.1 | None/None |
| prior_2 | +0 | 1800.2 |  | (3903) | 10580.7 | 7219.9 | None/None |
| wtop_q>6 | +6 | 1799.8 |  | (3904) | 10607.9 | 7244.2 | None/None |
| boost_above0_shift1 | +8 | 1798.7 |  | (3904) | 10618.3 | 7219.6 | None/None |
| shiftall_2 | +2 | 1801.2 |  | (3906) | 10635.9 | 7228.7 | None/None |
| boost_lt2 | +0 | 1806.2 |  | (3912) | 10682.7 | 7275.5 | None/None |
| boost_lt1<q | +2 | 1804.7 |  | (3912) | 10602.7 | 7218.2 | None/None |
| wtop_q>5 | +6 | 1802.7 |  | (3913) | 10628.6 | 7258.4 | None/None |
| primer_tail_first | +8 | 1802.3 |  | (3914) | 10598.8 | 7222.4 | None/None |
| wtop_q>4 | +6 | 1804.8 |  | (3916) | 10644.5 | 7262.8 | None/None |
| primer_twice | +2 | 1809.2 |  | (3919) | 10598.8 | 7239.4 | None/None |
| w_q+q//4 | +5 | 1811.7 |  | (3926) | 10676.7 | 7268.4 | None/None |
| prior_4 | +0 | 1817.2 |  | (3930) | 10594.3 | 7261.5 | None/None |
| boost_above_2 | +6 | 1815.9 |  | (3934) | 10582.3 | 7247.3 | None/None |
| boost_none | -10 | 1826.6 |  | (3935) | 10575.9 | 7387.1 | None/None |
| boost_lin_2 | +12 | 1812.7 |  | (3935) | 10777.5 | 7281.0 | None/None |
| boost_above_3 | +6 | 1821.3 |  | (3943) | 10579.2 | 7295.0 | None/None |
| w_q*3//4 | +5 | 1821.9 |  | (3943) | 10565.9 | 7317.6 | None/None |
| boost_above_4 | +6 | 1824.8 |  | (3948) | 10587.4 | 7343.5 | None/None |
| boost_bl_2 | +25 | 1813.1 |  | (3949) | 10769.6 | 7279.7 | None/None |
| col_u_first | +59 | 1795.3 |  | (3950) | 10590.5 | 7210.8 | None/None |
| word_alnum_first | +71 | 1788.3 | 1788.375 | 3951 | 10566.1 | 7170.0 | True/True |
| boost_above_5 | +6 | 1827.4 |  | (3952) | 10587.6 | 7365.2 | None/None |
| boost_above_6 | +6 | 1827.2 |  | (3952) | 10580.2 | 7380.7 | None/None |
| col_o1_first | +63 | 1795.8 |  | (3955) | 10602.3 | 7215.0 | None/None |
| tworate_min1 | +44 | 1808.3 |  | (3960) | 10703.1 | 7225.7 | None/None |
| word_ident_first | +82 | 1787.6 |  | (3961) | 10565.3 | 7178.6 | None/None |
| primer_defs | +8 | 1834.2 |  | (3965) | 10598.8 | 7226.1 | None/None |
| boost_lt1+lt2 | +11 | 1839.4 |  | (3981) | 11005.1 | 7365.3 | None/None |
| boost_bl_3 | +25 | 1835.6 |  | (3985) | 10914.6 | 7399.8 | None/None |
| boost_lin_3 | +12 | 1843.5 |  | (3988) | 10989.7 | 7436.6 | None/None |
| sse_avg7_b32_u | +103 | 1798.1 | 1799.5 | 4001 | 10497.5 | 7225.4 | True/True |
| boost_bl_4 | +25 | 1848.6 |  | (4009) | 10997.1 | 7494.7 | None/None |
| tworate_half | +40 | 1839.3 |  | (4009) | 10934.4 | 7393.5 | None/None |
| prior_8 | +0 | 1864.8 |  | (4010) | 10704.4 | 7394.4 | None/None |
| boost_bl_uncap | +18 | 1860.3 |  | (4021) | 11059.9 | 7573.1 | None/None |
| boost_bl_5 | +25 | 1856.7 |  | (4022) | 11034.1 | 7545.4 | None/None |
| boost_bl_6 | +25 | 1859.2 |  | (4026) | 11049.2 | 7564.0 | None/None |
| sse_avgh_b32_u | +103 | 1814.7 |  | (4029) | 10484.9 | 7298.8 | None/None |
| sse_avgh_b64_u | +103 | 1822.0 |  | (4041) | 10515.1 | 7306.4 | None/None |
| boost_lin_4 | +12 | 1876.9 |  | (4046) | 11189.2 | 7615.2 | None/None |
| combo_word_first+sse_avg7 | +174 | 1791.1 | 1792.625 | 4061 | 10461.0 | 7175.2 | True/True |
| match6_W6 | +166 | 1798.5 |  | (4062) | 10610.6 | 7216.2 | None/None |
| match6_W8 | +166 | 1811.6 |  | (4087) | 10665.8 | 7314.8 | None/None |
| match6_W8_cap32 | +174 | 1810.6 |  | (4093) | 10665.3 | 7313.3 | None/None |
| match8_W10 | +177 | 1818.4 |  | (4109) | 10702.5 | 7486.1 | None/None |
| sse_avg_b64 | +101 | 1865.0 |  | (4111) | 10800.4 | 7584.4 | None/None |
| sse_avg_b16_u | +101 | 1870.1 |  | (4120) | 10605.9 | 7595.4 | None/None |
| tworate_q4p1 | +42 | 1908.9 |  | (4127) | 10838.1 | 8355.0 | None/None |
| inherit_half | +22 | 1925.6 |  | (4137) | 11664.3 | 7922.2 | None/None |
| match6_W10 | +167 | 1842.4 |  | (4141) | 10801.2 | 7604.5 | None/None |
| match6_W10_cap16 | +175 | 1841.3 |  | (4148) | 10800.2 | 7587.3 | None/None |
| sse_avg_b64_u | +101 | 1893.3 |  | (4161) | 10681.4 | 7583.3 | None/None |
| sse_avg_b16 | +101 | 1894.6 |  | (4163) | 10932.3 | 7728.6 | None/None |
| sse_prod_b32_o1 | +92 | 1913.0 |  | (4187) | 11469.8 | 8040.5 | None/None |
| match6_W12 | +167 | 1885.9 |  | (4215) | 11006.4 | 8072.4 | None/None |
| sse_avg3_b32_u | +103 | 1961.0 |  | (4279) | 10931.5 | 7937.4 | None/None |
| sse_avg_b16_o1 | +105 | 1980.7 |  | (4313) | 10939.8 | 7904.7 | None/None |
| sse_prod_b32_u | +88 | 2043.3 |  | (4404) | 11736.3 | 8456.2 | None/None |
| prior_32 | +1 | 2134.1 |  | (4470) | 11596.1 | 8313.1 | None/None |
| sse_avg_b64_o1 | +105 | 2099.2 |  | (4514) | 11335.1 | 8322.6 | None/None |
| inherit_copy | +10 | 2165.6 |  | (4533) | 12508.4 | 10270.6 | None/None |
| sharp_pow2 | +5 | 2196.3 |  | (4582) | 12977.0 | 9182.6 | None/None |
| sharp_v*bl | +34 | 2205.1 |  | (4625) | 13044.9 | 9221.0 | None/None |
| word_alnum_last | +71 | 2449.7 |  | (5081) | 12989.2 | 9114.2 | None/None |
| word_ident_last | +82 | 2446.4 |  | (5087) | 12944.4 | 8845.7 | None/None |
| inherit_min4 | +26 | 2510.3 |  | (5137) | 14466.2 | 13819.0 | None/None |
| prior_128 | +2 | 2669.4 |  | (5388) | 13706.0 | 10803.7 | None/None |
| sharp_pow3 | +5 | 2878.0 |  | (5744) | 16841.2 | 12376.5 | None/None |
| inherit_min1 | +26 | 3044.0 |  | (6051) | 16539.6 | 15821.2 | None/None |
| inherit_min2 | +26 | 3107.4 |  | (6156) | 17341.8 | 17651.5 | None/None |
| col_u_last | +59 | 3422.4 |  | (6729) | 17547.1 | 15609.3 | None/None |

Totals in parentheses are ideal-bit estimates (ceil(ideal bits)); others exact. mono/T3 ideal unless an exact was run.

## Exact replacement texts (a.py lines; leading spaces are a.py's one-space indents)

### primer_d_last (+0 chars)
```
- def d(x,n,r):
-  z=[256**q-1 for q in(0,1,2,3,4,6,8,12,16)]
-  m,t,h=len(r),{},0
-  for i in range(m+n):
-   u=1
-   for j in range(8):
-    g=[t.setdefault((h&q,u),[0,0])for q in z]
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
-    s=sum(p)
-    if i<m:y=r[i]>>7-j&1
-    else:o=x%s;y=o>=p[0];x=x//s*p[y]+o-p[0]*y
-    for c in g:c[y],c[1-y]=c[y]+1,min(c[1-y],c[1-y]//4+2)
-    u=2*u+y
-   h=h<<8|u&255
-  return h.to_bytes(m+n,'big')[m:]
- q,n,v='0123456789abcdefghjkmnpqrstvwxyz',1,0
- def k(n,t):
-  for c in t:n=(n+c)*1000003
-  return''.join(q[n>>s&31]for s in(15,10,5,0))
+ q,n,v='0123456789abcdefghjkmnpqrstvwxyz',1,0
+ def k(n,t):
+  for c in t:n=(n+c)*1000003
+  return''.join(q[n>>s&31]for s in(15,10,5,0))
+ def d(x,n,r):
+  z=[256**q-1 for q in(0,1,2,3,4,6,8,12,16)]
+  m,t,h=len(r),{},0
+  for i in range(m+n):
+   u=1
+   for j in range(8):
+    g=[t.setdefault((h&q,u),[0,0])for q in z]
+    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    s=sum(p)
+    if i<m:y=r[i]>>7-j&1
+    else:o=x%s;y=o>=p[0];x=x//s*p[y]+o-p[0]*y
+    for c in g:c[y],c[1-y]=c[y]+1,min(c[1-y],c[1-y]//4+2)
+    u=2*u+y
+   h=h<<8|u&255
+  return h.to_bytes(m+n,'big')[m:]
```
### base (+0 chars)
```
```
### combo_dlast+wq-q//4 (+5 chars)
```
- def d(x,n,r):
-  z=[256**q-1 for q in(0,1,2,3,4,6,8,12,16)]
-  m,t,h=len(r),{},0
-  for i in range(m+n):
-   u=1
-   for j in range(8):
-    g=[t.setdefault((h&q,u),[0,0])for q in z]
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
-    s=sum(p)
-    if i<m:y=r[i]>>7-j&1
-    else:o=x%s;y=o>=p[0];x=x//s*p[y]+o-p[0]*y
-    for c in g:c[y],c[1-y]=c[y]+1,min(c[1-y],c[1-y]//4+2)
-    u=2*u+y
-   h=h<<8|u&255
-  return h.to_bytes(m+n,'big')[m:]
- q,n,v='0123456789abcdefghjkmnpqrstvwxyz',1,0
- def k(n,t):
-  for c in t:n=(n+c)*1000003
-  return''.join(q[n>>s&31]for s in(15,10,5,0))
+ q,n,v='0123456789abcdefghjkmnpqrstvwxyz',1,0
+ def k(n,t):
+  for c in t:n=(n+c)*1000003
+  return''.join(q[n>>s&31]for s in(15,10,5,0))
+ def d(x,n,r):
+  z=[256**q-1 for q in(0,1,2,3,4,6,8,12,16)]
+  m,t,h=len(r),{},0
+  for i in range(m+n):
+   u=1
+   for j in range(8):
+    g=[t.setdefault((h&q,u),[0,0])for q in z]
+    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    s=sum(p)
+    if i<m:y=r[i]>>7-j&1
+    else:o=x%s;y=o>=p[0];x=x//s*p[y]+o-p[0]*y
+    for c in g:c[y],c[1-y]=c[y]+1,min(c[1-y],c[1-y]//4+2)
+    u=2*u+y
+   h=h<<8|u&255
+  return h.to_bytes(m+n,'big')[m:]
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q-q//4+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
```
### w_q-q//4 (+5 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q-q//4+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
```
### primer_d_last+shiftall1 (+2 chars)
```
- def d(x,n,r):
-  z=[256**q-1 for q in(0,1,2,3,4,6,8,12,16)]
-  m,t,h=len(r),{},0
-  for i in range(m+n):
-   u=1
-   for j in range(8):
-    g=[t.setdefault((h&q,u),[0,0])for q in z]
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
-    s=sum(p)
-    if i<m:y=r[i]>>7-j&1
-    else:o=x%s;y=o>=p[0];x=x//s*p[y]+o-p[0]*y
-    for c in g:c[y],c[1-y]=c[y]+1,min(c[1-y],c[1-y]//4+2)
-    u=2*u+y
-   h=h<<8|u&255
-  return h.to_bytes(m+n,'big')[m:]
- q,n,v='0123456789abcdefghjkmnpqrstvwxyz',1,0
- def k(n,t):
-  for c in t:n=(n+c)*1000003
-  return''.join(q[n>>s&31]for s in(15,10,5,0))
+ q,n,v='0123456789abcdefghjkmnpqrstvwxyz',1,0
+ def k(n,t):
+  for c in t:n=(n+c)*1000003
+  return''.join(q[n>>s&31]for s in(15,10,5,0))
+ def d(x,n,r):
+  z=[256**q-1 for q in(0,1,2,3,4,6,8,12,16)]
+  m,t,h=len(r),{},0
+  for i in range(m+n):
+   u=1
+   for j in range(8):
+    g=[t.setdefault((h&q,u),[0,0])for q in z]
+    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    s=sum(p)
+    if i<m:y=r[i]>>7-j&1
+    else:o=x%s;y=o>=p[0];x=x//s*p[y]+o-p[0]*y
+    for c in g:c[y],c[1-y]=c[y]+1,min(c[1-y],c[1-y]//4+2)
+    u=2*u+y
+   h=h<<8|u&255
+  return h.to_bytes(m+n,'big')[m:]
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q+1+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
```
### combo_dlast+wq-(q>6) (+6 chars)
```
- def d(x,n,r):
-  z=[256**q-1 for q in(0,1,2,3,4,6,8,12,16)]
-  m,t,h=len(r),{},0
-  for i in range(m+n):
-   u=1
-   for j in range(8):
-    g=[t.setdefault((h&q,u),[0,0])for q in z]
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
-    s=sum(p)
-    if i<m:y=r[i]>>7-j&1
-    else:o=x%s;y=o>=p[0];x=x//s*p[y]+o-p[0]*y
-    for c in g:c[y],c[1-y]=c[y]+1,min(c[1-y],c[1-y]//4+2)
-    u=2*u+y
-   h=h<<8|u&255
-  return h.to_bytes(m+n,'big')[m:]
- q,n,v='0123456789abcdefghjkmnpqrstvwxyz',1,0
- def k(n,t):
-  for c in t:n=(n+c)*1000003
-  return''.join(q[n>>s&31]for s in(15,10,5,0))
+ q,n,v='0123456789abcdefghjkmnpqrstvwxyz',1,0
+ def k(n,t):
+  for c in t:n=(n+c)*1000003
+  return''.join(q[n>>s&31]for s in(15,10,5,0))
+ def d(x,n,r):
+  z=[256**q-1 for q in(0,1,2,3,4,6,8,12,16)]
+  m,t,h=len(r),{},0
+  for i in range(m+n):
+   u=1
+   for j in range(8):
+    g=[t.setdefault((h&q,u),[0,0])for q in z]
+    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    s=sum(p)
+    if i<m:y=r[i]>>7-j&1
+    else:o=x%s;y=o>=p[0];x=x//s*p[y]+o-p[0]*y
+    for c in g:c[y],c[1-y]=c[y]+1,min(c[1-y],c[1-y]//4+2)
+    u=2*u+y
+   h=h<<8|u&255
+  return h.to_bytes(m+n,'big')[m:]
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q-(q>6)+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
```
### shiftall_1 (+2 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q+1+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
```
### w_q-(q>6) (+6 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q-(q>6)+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
```
### boost_above_0 (+6 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q+(c[1-y]<1)*(q>0)for(q,c)in enumerate(g))for y in(0,1)]
```
### wtop_q>7 (+6 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q+(q>7)+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
```
### prior_2 (+0 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[2+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
```
### wtop_q>6 (+6 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q+(q>6)+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
```
### boost_above0_shift1 (+8 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q+1+(c[1-y]<1)*(q>0)for(q,c)in enumerate(g))for y in(0,1)]
```
### shiftall_2 (+2 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q+2+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
```
### boost_lt2 (+0 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q+(c[1-y]<2)for(q,c)in enumerate(g))for y in(0,1)]
```
### boost_lt1<q (+2 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q+(c[1-y]<1<q)for(q,c)in enumerate(g))for y in(0,1)]
```
### wtop_q>5 (+6 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q+(q>5)+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
```
### primer_tail_first (+8 chars)
```
- r=d(v,4565,a)
+ r=d(v,4565,a[608:]+a)
```
### wtop_q>4 (+6 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q+(q>4)+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
```
### primer_twice (+2 chars)
```
- r=d(v,4565,a)
+ r=d(v,4565,a+a)
```
### w_q+q//4 (+5 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q+q//4+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
```
### prior_4 (+0 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[4+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
```
### boost_above_2 (+6 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q+(c[1-y]<1)*(q>2)for(q,c)in enumerate(g))for y in(0,1)]
```
### boost_none (-10 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q for(q,c)in enumerate(g))for y in(0,1)]
```
### boost_lin_2 (+12 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q+(c[1-y]<1)*min(c[y],2)for(q,c)in enumerate(g))for y in(0,1)]
```
### boost_above_3 (+6 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q+(c[1-y]<1)*(q>3)for(q,c)in enumerate(g))for y in(0,1)]
```
### w_q*3//4 (+5 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q*3//4+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
```
### boost_above_4 (+6 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q+(c[1-y]<1)*(q>4)for(q,c)in enumerate(g))for y in(0,1)]
```
### boost_bl_2 (+25 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q+(c[1-y]<1)*min(c[y].bit_length(),2)for(q,c)in enumerate(g))for y in(0,1)]
```
### col_u_first (+59 chars)
```
-  m,t,h=len(r),{},0
+  m,t,h,w=len(r),{},0,0
-    g=[t.setdefault((h&q,u),[0,0])for q in z]
+    g=[t.setdefault((w,u,2),[0,0])]+[t.setdefault((h&q,u),[0,0])for q in z]
-   h=h<<8|u&255
+   h=h<<8|u&255
+   b=u&255;w=(w+1)*(b!=10)
```
### word_alnum_first (+71 chars)
```
-  m,t,h=len(r),{},0
+  m,t,h,w=len(r),{},0,0
-    g=[t.setdefault((h&q,u),[0,0])for q in z]
+    g=[t.setdefault((w,u,0),[0,0])]+[t.setdefault((h&q,u),[0,0])for q in z]
-   h=h<<8|u&255
+   h=h<<8|u&255
+   b=u&255;w=(w<<8|b)*chr(b).isalnum()
```
### boost_above_5 (+6 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q+(c[1-y]<1)*(q>5)for(q,c)in enumerate(g))for y in(0,1)]
```
### boost_above_6 (+6 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q+(c[1-y]<1)*(q>6)for(q,c)in enumerate(g))for y in(0,1)]
```
### col_o1_first (+63 chars)
```
-  m,t,h=len(r),{},0
+  m,t,h,w=len(r),{},0,0
-    g=[t.setdefault((h&q,u),[0,0])for q in z]
+    g=[t.setdefault((w,h&255,u),[0,0])]+[t.setdefault((h&q,u),[0,0])for q in z]
-   h=h<<8|u&255
+   h=h<<8|u&255
+   b=u&255;w=(w+1)*(b!=10)
```
### tworate_min1 (+44 chars)
```
-    g=[t.setdefault((h&q,u),[0,0])for q in z]
+    g=[t.setdefault((h&q,u),[0]*4)for q in z]
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]+c[y+2]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
-    for c in g:c[y],c[1-y]=c[y]+1,min(c[1-y],c[1-y]//4+2)
+    for c in g:c[y],c[1-y],c[y+2],c[3-y]=c[y]+1,min(c[1-y],c[1-y]//4+2),c[y+2]+1,min(c[3-y],1)
```
### word_ident_first (+82 chars)
```
-  m,t,h=len(r),{},0
+  m,t,h,w=len(r),{},0,0
-    g=[t.setdefault((h&q,u),[0,0])for q in z]
+    g=[t.setdefault((w,u,0),[0,0])]+[t.setdefault((h&q,u),[0,0])for q in z]
-   h=h<<8|u&255
+   h=h<<8|u&255
+   b=u&255;w=(w<<8|b)*('a'+chr(b)).isidentifier()
```
### primer_defs (+8 chars)
```
- r=d(v,4565,a)
+ r=d(v,4565,a[39:608])
```
### boost_lt1+lt2 (+11 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q+(c[1-y]<1)+(c[1-y]<2)for(q,c)in enumerate(g))for y in(0,1)]
```
### boost_bl_3 (+25 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q+(c[1-y]<1)*min(c[y].bit_length(),3)for(q,c)in enumerate(g))for y in(0,1)]
```
### boost_lin_3 (+12 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q+(c[1-y]<1)*min(c[y],3)for(q,c)in enumerate(g))for y in(0,1)]
```
### sse_avg7_b32_u (+103 chars)
```
-    s=sum(p)
+    s=sum(p)
+    c=t.setdefault((p[0]*32//s,u,1),[0,0]);g+=[c];p=[7*p[y]*(sum(c)+2)+s*(c[y]+1)for y in(0,1)];s=sum(p)
```
### boost_bl_4 (+25 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q+(c[1-y]<1)*min(c[y].bit_length(),4)for(q,c)in enumerate(g))for y in(0,1)]
```
### tworate_half (+40 chars)
```
-    g=[t.setdefault((h&q,u),[0,0])for q in z]
+    g=[t.setdefault((h&q,u),[0]*4)for q in z]
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]+c[y+2]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
-    for c in g:c[y],c[1-y]=c[y]+1,min(c[1-y],c[1-y]//4+2)
+    for c in g:c[y],c[1-y],c[y+2],c[3-y]=c[y]+1,min(c[1-y],c[1-y]//4+2),c[y+2]+1,c[3-y]//2
```
### prior_8 (+0 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[8+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
```
### boost_bl_uncap (+18 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q+(c[1-y]<1)*c[y].bit_length()for(q,c)in enumerate(g))for y in(0,1)]
```
### boost_bl_5 (+25 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q+(c[1-y]<1)*min(c[y].bit_length(),5)for(q,c)in enumerate(g))for y in(0,1)]
```
### boost_bl_6 (+25 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q+(c[1-y]<1)*min(c[y].bit_length(),6)for(q,c)in enumerate(g))for y in(0,1)]
```
### sse_avgh_b32_u (+103 chars)
```
-    s=sum(p)
+    s=sum(p)
+    c=t.setdefault((p[0]*32//s,u,1),[0,0]);g+=[c];p=[3*p[y]*(sum(c)+2)+s*(c[y]+1)for y in(0,1)];s=sum(p)
```
### sse_avgh_b64_u (+103 chars)
```
-    s=sum(p)
+    s=sum(p)
+    c=t.setdefault((p[0]*64//s,u,1),[0,0]);g+=[c];p=[3*p[y]*(sum(c)+2)+s*(c[y]+1)for y in(0,1)];s=sum(p)
```
### boost_lin_4 (+12 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q+(c[1-y]<1)*min(c[y],4)for(q,c)in enumerate(g))for y in(0,1)]
```
### combo_word_first+sse_avg7 (+174 chars)
```
-  m,t,h=len(r),{},0
+  m,t,h,w=len(r),{},0,0
-    g=[t.setdefault((h&q,u),[0,0])for q in z]
+    g=[t.setdefault((w,u,0),[0,0])]+[t.setdefault((h&q,u),[0,0])for q in z]
-   h=h<<8|u&255
+   h=h<<8|u&255
+   b=u&255;w=(w<<8|b)*chr(b).isalnum()
-    s=sum(p)
+    s=sum(p)
+    c=t.setdefault((p[0]*32//s,u,1),[0,0]);g+=[c];p=[7*p[y]*(sum(c)+2)+s*(c[y]+1)for y in(0,1)];s=sum(p)
```
### match6_W6 (+166 chars)
```
-  m,t,h=len(r),{},0
+  m,t,h,M,B,P,L=len(r),{},0,{},[0],0,0
-   u=1
+   u=1;e=B[P]|256
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))+(L*(e>>8-j==u)*(e>>7-j&1==y)<<6)for y in(0,1)]
-   h=h<<8|u&255
+   h=h<<8|u&255;b=u&255;L=(L+1)*(B[P]==b);B+=[b];P=P+1if L else M.get(h&281474976710655,0);M[h&281474976710655]=len(B)
```
### match6_W8 (+166 chars)
```
-  m,t,h=len(r),{},0
+  m,t,h,M,B,P,L=len(r),{},0,{},[0],0,0
-   u=1
+   u=1;e=B[P]|256
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))+(L*(e>>8-j==u)*(e>>7-j&1==y)<<8)for y in(0,1)]
-   h=h<<8|u&255
+   h=h<<8|u&255;b=u&255;L=(L+1)*(B[P]==b);B+=[b];P=P+1if L else M.get(h&281474976710655,0);M[h&281474976710655]=len(B)
```
### match6_W8_cap32 (+174 chars)
```
-  m,t,h=len(r),{},0
+  m,t,h,M,B,P,L=len(r),{},0,{},[0],0,0
-   u=1
+   u=1;e=B[P]|256
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))+(min(L,32)*(e>>8-j==u)*(e>>7-j&1==y)<<8)for y in(0,1)]
-   h=h<<8|u&255
+   h=h<<8|u&255;b=u&255;L=(L+1)*(B[P]==b);B+=[b];P=P+1if L else M.get(h&281474976710655,0);M[h&281474976710655]=len(B)
```
### match8_W10 (+177 chars)
```
-  m,t,h=len(r),{},0
+  m,t,h,M,B,P,L=len(r),{},0,{},[0],0,0
-   u=1
+   u=1;e=B[P]|256
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))+(L*(e>>8-j==u)*(e>>7-j&1==y)<<10)for y in(0,1)]
-   h=h<<8|u&255
+   h=h<<8|u&255;b=u&255;L=(L+1)*(B[P]==b);B+=[b];P=P+1if L else M.get(h&18446744073709551615,0);M[h&18446744073709551615]=len(B)
```
### sse_avg_b64 (+101 chars)
```
-    s=sum(p)
+    s=sum(p)
+    c=t.setdefault((p[0]*64//s,1,1),[0,0]);g+=[c];p=[p[y]*(sum(c)+2)+s*(c[y]+1)for y in(0,1)];s=sum(p)
```
### sse_avg_b16_u (+101 chars)
```
-    s=sum(p)
+    s=sum(p)
+    c=t.setdefault((p[0]*16//s,u,1),[0,0]);g+=[c];p=[p[y]*(sum(c)+2)+s*(c[y]+1)for y in(0,1)];s=sum(p)
```
### tworate_q4p1 (+42 chars)
```
-    g=[t.setdefault((h&q,u),[0,0])for q in z]
+    g=[t.setdefault((h&q,u),[0]*4)for q in z]
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]+c[y+2]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
-    for c in g:c[y],c[1-y]=c[y]+1,min(c[1-y],c[1-y]//4+2)
+    for c in g:c[y],c[1-y],c[y+2],c[3-y]=c[y]+1,min(c[1-y],c[1-y]//4+2),c[y+2]+1,c[3-y]//4+1
```
### inherit_half (+22 chars)
```
-    g=[t.setdefault((h&q,u),[0,0])for q in z]
+    c=[0,0];g=[c:=t.setdefault((h&q,u),[v//2for v in c])for q in z]
```
### match6_W10 (+167 chars)
```
-  m,t,h=len(r),{},0
+  m,t,h,M,B,P,L=len(r),{},0,{},[0],0,0
-   u=1
+   u=1;e=B[P]|256
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))+(L*(e>>8-j==u)*(e>>7-j&1==y)<<10)for y in(0,1)]
-   h=h<<8|u&255
+   h=h<<8|u&255;b=u&255;L=(L+1)*(B[P]==b);B+=[b];P=P+1if L else M.get(h&281474976710655,0);M[h&281474976710655]=len(B)
```
### match6_W10_cap16 (+175 chars)
```
-  m,t,h=len(r),{},0
+  m,t,h,M,B,P,L=len(r),{},0,{},[0],0,0
-   u=1
+   u=1;e=B[P]|256
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))+(min(L,16)*(e>>8-j==u)*(e>>7-j&1==y)<<10)for y in(0,1)]
-   h=h<<8|u&255
+   h=h<<8|u&255;b=u&255;L=(L+1)*(B[P]==b);B+=[b];P=P+1if L else M.get(h&281474976710655,0);M[h&281474976710655]=len(B)
```
### sse_avg_b64_u (+101 chars)
```
-    s=sum(p)
+    s=sum(p)
+    c=t.setdefault((p[0]*64//s,u,1),[0,0]);g+=[c];p=[p[y]*(sum(c)+2)+s*(c[y]+1)for y in(0,1)];s=sum(p)
```
### sse_avg_b16 (+101 chars)
```
-    s=sum(p)
+    s=sum(p)
+    c=t.setdefault((p[0]*16//s,1,1),[0,0]);g+=[c];p=[p[y]*(sum(c)+2)+s*(c[y]+1)for y in(0,1)];s=sum(p)
```
### sse_prod_b32_o1 (+92 chars)
```
-    s=sum(p)
+    s=sum(p)
+    c=t.setdefault((p[0]*32//s,h&255,u),[0,0]);g+=[c];p=[p[y]*(c[y]+1)for y in(0,1)];s=sum(p)
```
### match6_W12 (+167 chars)
```
-  m,t,h=len(r),{},0
+  m,t,h,M,B,P,L=len(r),{},0,{},[0],0,0
-   u=1
+   u=1;e=B[P]|256
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))+(L*(e>>8-j==u)*(e>>7-j&1==y)<<12)for y in(0,1)]
-   h=h<<8|u&255
+   h=h<<8|u&255;b=u&255;L=(L+1)*(B[P]==b);B+=[b];P=P+1if L else M.get(h&281474976710655,0);M[h&281474976710655]=len(B)
```
### sse_avg3_b32_u (+103 chars)
```
-    s=sum(p)
+    s=sum(p)
+    c=t.setdefault((p[0]*32//s,u,1),[0,0]);g+=[c];p=[p[y]*(sum(c)+2)+3*s*(c[y]+1)for y in(0,1)];s=sum(p)
```
### sse_avg_b16_o1 (+105 chars)
```
-    s=sum(p)
+    s=sum(p)
+    c=t.setdefault((p[0]*16//s,h&255,u),[0,0]);g+=[c];p=[p[y]*(sum(c)+2)+s*(c[y]+1)for y in(0,1)];s=sum(p)
```
### sse_prod_b32_u (+88 chars)
```
-    s=sum(p)
+    s=sum(p)
+    c=t.setdefault((p[0]*32//s,u,1),[0,0]);g+=[c];p=[p[y]*(c[y]+1)for y in(0,1)];s=sum(p)
```
### prior_32 (+1 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[32+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
```
### sse_avg_b64_o1 (+105 chars)
```
-    s=sum(p)
+    s=sum(p)
+    c=t.setdefault((p[0]*64//s,h&255,u),[0,0]);g+=[c];p=[p[y]*(sum(c)+2)+s*(c[y]+1)for y in(0,1)];s=sum(p)
```
### inherit_copy (+10 chars)
```
-    g=[t.setdefault((h&q,u),[0,0])for q in z]
+    c=[0,0];g=[c:=t.setdefault((h&q,u),c[:])for q in z]
```
### sharp_pow2 (+5 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[(1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g)))**2for y in(0,1)]
```
### sharp_v*bl (+34 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[(1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g)))for y in(0,1)]
-    s=sum(p)
+    p=[v<<v.bit_length()for v in p];s=sum(p)
```
### word_alnum_last (+71 chars)
```
-  m,t,h=len(r),{},0
+  m,t,h,w=len(r),{},0,0
-    g=[t.setdefault((h&q,u),[0,0])for q in z]
+    g=[t.setdefault((h&q,u),[0,0])for q in z]+[t.setdefault((w,u,0),[0,0])]
-   h=h<<8|u&255
+   h=h<<8|u&255
+   b=u&255;w=(w<<8|b)*chr(b).isalnum()
```
### word_ident_last (+82 chars)
```
-  m,t,h=len(r),{},0
+  m,t,h,w=len(r),{},0,0
-    g=[t.setdefault((h&q,u),[0,0])for q in z]
+    g=[t.setdefault((h&q,u),[0,0])for q in z]+[t.setdefault((w,u,0),[0,0])]
-   h=h<<8|u&255
+   h=h<<8|u&255
+   b=u&255;w=(w<<8|b)*('a'+chr(b)).isidentifier()
```
### inherit_min4 (+26 chars)
```
-    g=[t.setdefault((h&q,u),[0,0])for q in z]
+    c=[0,0];g=[c:=t.setdefault((h&q,u),[min(v,4)for v in c])for q in z]
```
### prior_128 (+2 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[128+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
```
### sharp_pow3 (+5 chars)
```
-    p=[1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g))for y in(0,1)]
+    p=[(1+sum(c[y]<<q+(c[1-y]<1)for(q,c)in enumerate(g)))**3for y in(0,1)]
```
### inherit_min1 (+26 chars)
```
-    g=[t.setdefault((h&q,u),[0,0])for q in z]
+    c=[0,0];g=[c:=t.setdefault((h&q,u),[min(v,1)for v in c])for q in z]
```
### inherit_min2 (+26 chars)
```
-    g=[t.setdefault((h&q,u),[0,0])for q in z]
+    c=[0,0];g=[c:=t.setdefault((h&q,u),[min(v,2)for v in c])for q in z]
```
### col_u_last (+59 chars)
```
-  m,t,h=len(r),{},0
+  m,t,h,w=len(r),{},0,0
-    g=[t.setdefault((h&q,u),[0,0])for q in z]
+    g=[t.setdefault((h&q,u),[0,0])for q in z]+[t.setdefault((w,u,2),[0,0])]
-   h=h<<8|u&255
+   h=h<<8|u&255
+   b=u&255;w=(w+1)*(b!=10)
```
