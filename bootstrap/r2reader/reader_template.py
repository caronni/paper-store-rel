"""reader_template.py -- the ONE source of the long form of the typed
stage-2 reader (ruling 35 of RECORD-2026-10-20; the pattern of
bootstrap/stage1/template.py, ruling 43).  Since ruling 48 (2026-10-22) it
lives beside the typed reader: the long form is GENERATED from the short
form, which is the source.

TEMPLATE is the typed region of bootstrap/r2reader/reader_lite_v1.py -- the
text between the lines '# BEGIN READER' and '# END READER', as
loader/make_typed.py's region() cuts it -- with every name the reader binds
written as a ROLE: a capitalised token for one binding of one scope.  A
comprehension is a scope of its own, so one letter bound in two scopes is
two roles; within one scope, a letter that serves two purposes one after
the other is two roles as well (splits(): dd's sz, v's r, ft's k and ld's
k -- the two k of a 'k,k,m,n=max(...)' unpack are the score and the tie
key).  The typed layout is kept, every line break and space.  The block
from '#--- shared with the loader (not typed) ---' to '#--- end shared ---'
is the loader's decoder d, verbatim: not typed, not renamed
(count_reader.py and make_typed.py drop it; it is in the file only so that
the file runs on its own).  When the typed text changes, the template is
re-marked from it: changeset/reroll_template.py resolves every name of the
typed text to its scope and writes the roles by (scope, letter), the splits
by line; ROLE_TABLE below follows the letters.

Two texts are derived from TEMPLATE and nothing else is a source:
  - the typed text, rename(TEMPLATE, LETTERS), which must equal the region
    of reader_lite_v1.py byte for byte;
  - the long form reader_long_v1.py (gen_reader_long.py): rename(TEMPLATE,
    LONG_NAMES) laid out by the ast, with comments; its ast, every long name
    mapped back to its role, must equal the template's.
The free names of the typed text are d (the loader's decoder), N2 and B2
(tokens the build replaces by the bundle's length and CRC-32), builtins and
methods.

check_bindings() proves that the roles are the typed program's bindings:
every occurrence of a role resolves, in the typed text, to the scope the
role is bound in, and every other name is free.  check_splits() proves that
each letter split into two roles within one scope can be two variables: no
load of one role can see a value stored under the other.  check_long_names()
proves the long names distinct, none a keyword, a builtin, d, N2, B2, a
method name of the text or a name of the shared block.  Together: the long
form is the typed program with its variables renamed.
test_reader_identity.py runs all of it.
"""
import ast
import builtins
import io
import keyword
import os
import re
import tokenize

HERE = os.path.dirname(os.path.abspath(__file__))
READER = os.path.join(HERE, 'reader_lite_v1.py')
BEGIN, END = '# BEGIN READER', '# END READER'
SHARED_BEGIN = '#--- shared with the loader (not typed) ---'
SHARED_END = '#--- end shared ---'
FREE = frozenset(('d', 'N2', 'B2'))     # the free names beside builtins

TEMPLATE = """#--- shared with the loader (not typed) ---
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
def Load(Load_Name):
 Load_Raw=open(Load_Name,'rb').read()
 Load_W,Load_H=[int(Load_Field)for Load_Field in Load_Raw[:64].split()[1:3]]
 return Load_W,Load_H,Load_Raw[len(Load_Raw)-Load_H*Load_W:]+Load_H*bytes([128])*Load_W
def Fit(Fit_Block,Fit_Pitch):
 Fit_Dx=Fit_Dy=0
 for Fit_Step in(Fit_Pitch>>5,Fit_Pitch>>6,Fit_Pitch>>7,Fit_Pitch>>8):
  Fit_Best,Fit_Tie,Fit_Dx,Fit_Dy=max((Score([Fit_Block[0]+Fit_Tx,Fit_Block[1]+Fit_Ty]+Fit_Block[2:])*(1-2*Fit_Block[4]),-abs(Fit_Tx-Fit_Dx)-abs(Fit_Ty-Fit_Dy)
   ,Fit_Tx,Fit_Ty)for Fit_Tx in(Fit_Dx-Fit_Step,Fit_Dx,Fit_Dx+Fit_Step)for Fit_Ty in(Fit_Dy-Fit_Step,Fit_Dy,Fit_Dy+Fit_Step))
 Fit_Block[0]+=Fit_Dx
 Fit_Block[1]+=Fit_Dy
def Crc(Crc_Data):
 Crc_Reg=2**32-1
 for Crc_Byte in Crc_Data:
  Crc_Reg=Crc_Byte^Crc_Reg
  for Crc_Shift in range(8):Crc_Reg=Crc_Reg>>1^3988292384*(Crc_Reg&1)
 return Crc_Reg^2**32-1
def Spot(Spot_Block,Spot_Dx,Spot_Dy):
 return Spot_Block[0]+(Spot_Block[2][0]*Spot_Dx+Spot_Block[3][0]*Spot_Dy)//17,Spot_Block[1]+(Spot_Block[2][1]*Spot_Dx+Spot_Block[3][1]*Spot_Dy)//17
Rings=[(Rings_Dx,Rings_Dy,sum(Rings_Dx*Rings_Dx+Rings_Dy*Rings_Dy>Rings_I*Rings_I+Rings_I for Rings_I in range(7))&1<1)
 for Rings_Dy in range(-7,8)for Rings_Dx in range(-7,8)if Rings_Dx*Rings_Dx+Rings_Dy*Rings_Dy<57]
Cells=[(Cells_Dx,Cells_Dy)for Cells_Dy in range(-8,8)for Cells_Dx in range(-8,8)]
Head=[(Head_Dx,Head_Dy)for Head_Dx,Head_Dy in Cells if Head_Dx*Head_Dx+Head_Dy*Head_Dy>56][:68]
Timing=[(Timing_Dx,Timing_Dy,Timing_Dx+Timing_Dy&1)for Timing_Dy in range(-9,9)for Timing_Dx in range(-9,9)
 if{Timing_Dx,Timing_Dy}&{-9,8}]
def Axes(Axes_X,Axes_Y,Axes_P,Axes_R,Axes_T):
 Axes_Cos=4096-(Axes_R*Axes_R>>13)
 Axes_A=[17*Axes_P*Axes_Cos>>16,17*Axes_P*Axes_R>>16]
 Axes_B=[-17*Axes_P*Axes_R>>16,17*Axes_P*Axes_Cos>>16]
 for Axes_I in range(Axes_T):Axes_A,Axes_B=Axes_B,[-Axes_A[0],-Axes_A[1]]
 return[Axes_X,Axes_Y,Axes_A,Axes_B]
def Sample(Sample_Block):
 Sample_Grey={(Sample_Dx,Sample_Dy):Grey(*Spot(Sample_Block,Sample_Dx,Sample_Dy))for Sample_Dy in range(-9,9)for Sample_Dx in range(-9,9)}
 Sample_Sorted=sorted(Sample_Grey[Sample_Tx,Sample_Ty]for Sample_Tx,Sample_Ty,Sample_Tk in Timing)
 return Sample_Grey,Sample_Sorted[8]+Sample_Sorted[59]>>1
def Grey(Grey_X,Grey_Y):
 Grey_Fx,Grey_Fy,Grey_I=Grey_X&15,Grey_Y&15,(Grey_Y>>4)*Width+(Grey_X>>4)
 return((Pixels[Grey_I]*(16-Grey_Fx)+Pixels[Grey_I+1]*Grey_Fx)*(16-Grey_Fy)
  +(Pixels[Grey_I+Width]*(16-Grey_Fx)+Pixels[Grey_I+Width+1]*Grey_Fx)*Grey_Fy)>>8
def Score(Score_Seed):
 return sum(Grey(*Spot(Score_Seed,Score_Dx,Score_Dy))*(1-2*Score_K)for Score_Dx,Score_Dy,Score_K in Timing)
def Bulls(Bulls_Bits):
 Bulls_Found=[]
 for Bulls_Row in range(Height):
  for Bulls_C4,Bulls_Span in Combs(Bulls_Bits[Width*Bulls_Row:Width*Bulls_Row+Width]):
   Bulls_Col=Bulls_C4+2>>2
   if[Bulls_Near for Bulls_Near in Bulls_Found if 16*abs(Bulls_Near[1]-4*Bulls_C4)+16*abs(Bulls_Near[2]-16*Bulls_Row)<6*Bulls_Near[3]]:
    continue
   Bulls_Top,Bulls_End=max(0,Bulls_Row-Bulls_Span//2-2),min(Height,Bulls_Row+Bulls_Span//2+3)
   Bulls_Miss,Bulls_R4,Bulls_CSpan=min([(abs(Bulls_Cr-4*(Bulls_Row-Bulls_Top)),Bulls_Cr,Bulls_Ct)for Bulls_Cr,Bulls_Ct in Combs(Bulls_Bits[Width*Bulls_Top+Bulls_Col:Width*Bulls_End:Width])]
    +[(Bulls_Span,0,0)])
   if Bulls_Span<6*Bulls_Miss:continue
   Bulls_P,Bulls_X,Bulls_Y=(Bulls_Span+Bulls_CSpan)*16//3,4*Bulls_C4,4*(Bulls_R4+4*Bulls_Top)
   if min(Bulls_X,Bulls_Y)<Bulls_P//2 or Bulls_X>16*Width-Bulls_P//2-32 or Bulls_Y>16*Height-Bulls_P//2-32:continue
   Bulls_Hits=sum(Bulls_Bits[(Bulls_Y+(Bulls_Ry*Bulls_P>>4)+8>>4)*Width+(Bulls_X+(Bulls_Rx*Bulls_P>>4)+8>>4)]==Bulls_Rk for Bulls_Rx,Bulls_Ry,Bulls_Rk in Rings)
   if 4*Bulls_Hits>=len(Rings)*3:Bulls_Found+=[(Bulls_Hits,Bulls_X,Bulls_Y,Bulls_P)]
 return Bulls_Found
def Walk(Walk_Pitch,Walk_Queue):
 Walk_Seen={}
 Walk_Cell,Walk_Placed=5*Walk_Pitch>>4,{}
 Walk_Got=[]
 for Walk_Block in Walk_Queue:
  Walk_Cx=Walk_Block[0]//Walk_Cell
  Walk_Cy=Walk_Block[1]//Walk_Cell
  if(Walk_Cx,Walk_Cy)in Walk_Seen:continue
  Walk_Seen[Walk_Cx,Walk_Cy]=1
  if min(Walk_Block[0],Walk_Block[1],16*Width-32-Walk_Block[0],16*Height-32-Walk_Block[1])<5*Walk_Pitch>>3:continue
  Walk_Seed,Walk_Row,Walk_Col=Walk_Block[5]
  if Walk_Row or Walk_Col:
   Fit(Walk_Block,Walk_Pitch)
   for Walk_Axis,Walk_Along in((2,Walk_Col),(3,Walk_Row)):
    Walk_Sign=(Walk_Along>0)-(Walk_Along<0)
    Walk_Nbr=Walk_Placed.get((Walk_Seed,Walk_Row-Walk_Sign*(Walk_Axis>2),Walk_Col-Walk_Sign*(Walk_Axis<3)))
    if Walk_Nbr and Walk_Sign:Walk_Block[Walk_Axis]=[Walk_Sign*(Walk_Block[0]-Walk_Nbr[0]),Walk_Sign*(Walk_Block[1]-Walk_Nbr[1])]
  Walk_Read=(Walk_Row or Walk_Col)and Read(Walk_Block)
  if Walk_Read:Walk_Got+=[Walk_Read]
  if Walk_Read!=None:
   Walk_Placed[Walk_Seed,Walk_Row,Walk_Col]=Walk_Block
   Walk_Queue+=[[Walk_Block[0]+Walk_Sgn*Walk_Block[2+Walk_Dir//2][0],Walk_Block[1]+Walk_Sgn*Walk_Block[2+Walk_Dir//2][1],Walk_Block[2],Walk_Block[3],1-Walk_Block[4],
    (Walk_Seed,Walk_Row+Walk_Sgn*(Walk_Dir>1),Walk_Col+Walk_Sgn*(Walk_Dir<2))]for Walk_Dir in range(4)for Walk_Sgn in[1-2*(Walk_Dir&1)]]
 return Walk_Got
def Combs(Combs_Line):
 Combs_Edges,Combs_Bit,Combs_At=[0],Combs_Line[0],0
 while Combs_At>=0:
  Combs_At=Combs_Line.find(1-Combs_Bit,Combs_At)
  if Combs_At>0:Combs_Bit,Combs_Edges=1-Combs_Bit,Combs_Edges+[Combs_At]
 Combs_Edges+=[len(Combs_Line)]
 return[(Combs_First+Combs_Edges[Combs_Run+12]+Combs_Edges[Combs_Run+13]-2,Combs_Span)for Combs_Run in range(1+Combs_Line[0],len(Combs_Edges)-14,2)
  for Combs_First,Combs_Span in[(Combs_Edges[Combs_Run]+Combs_Edges[Combs_Run+1],Combs_Edges[Combs_Run+12]+Combs_Edges[Combs_Run+13]-Combs_Edges[Combs_Run]-Combs_Edges[Combs_Run+1])]
  if Combs_Span>23 and min(Combs_Edges[Combs_Run]-Combs_Edges[Combs_Run-1],Combs_Edges[Combs_Run+14]-Combs_Edges[Combs_Run+13])*96>=Combs_Span and max(
  abs(12*(Combs_Edges[Combs_Run+Combs_K+6]+Combs_Edges[Combs_Run+Combs_K+7]-Combs_First)-(Combs_K+6)*Combs_Span)for Combs_K in(-5,5,-4,4,-3,3,-2,2)
  )<=(3*Combs_Span+144)//10]
def Read(Read_Block):
 Read_Grey,Read_Thr=Sample(Read_Block)
 return Bits(Read_Grey,Read_Thr,Cells,32)if sum(Read_Grey[Read_Dx,Read_Dy]<Read_Thr for Read_Dx,Read_Dy in Cells)>3 else b''
def Bits(Bits_Grey,Bits_Thr,Bits_Mods,Bits_Check):
 Bits_N=len(Bits_Mods)
 Bits_Read=int(''.join('01'[Bits_Thr-Bits_Grey[Bits_Dx,Bits_Dy]+(Bits_Grey[Bits_Dx-1,Bits_Dy]+Bits_Grey[Bits_Dx+1,Bits_Dy]+Bits_Grey[Bits_Dx,Bits_Dy-1]+Bits_Grey[Bits_Dx,Bits_Dy+1]
  -4*Bits_Grey[Bits_Dx,Bits_Dy]>>1)>0]for Bits_Dx,Bits_Dy in Bits_Mods),2)
 for Bits_Flip in[0]+[1<<Bits_K for Bits_K in range(Bits_N*(Bits_Check>20))]:
  Bits_Cand=Bits_Read^Bits_Flip
  if Crc(Header+(Bits_Cand>>Bits_Check).to_bytes((Bits_N-Bits_Check)//8))%2**Bits_Check==Bits_Cand%2**Bits_Check:
   return(Bits_Cand>>Bits_Check).to_bytes((Bits_N-Bits_Check)//8)
def Pose():
 Pose_Bulls=Bulls(Pixels.translate(bytes(Pose_G<Pose_Thr for Pose_Thr in[min(Pixels[::97])+max(Pixels[::97])>>1]
  for Pose_G in range(256))))
 Pose_Best,Pose_Tie,Pose_Rot,Pose_Turns=max((sum(abs(Score(Axes(Pose_Cx,Pose_Cy,Pose_Cp,Pose_Tr,Pose_Tt)))for Pose_Ck,Pose_Cx,Pose_Cy,Pose_Cp in Pose_Bulls),-abs(Pose_Tr),Pose_Tr,Pose_Tt)
  for Pose_Tr in range(-640,641,64)for Pose_Tt in range(4))
 Pose_Seeds=[]
 for Pose_Hits,Pose_X,Pose_Y,Pose_P in Pose_Bulls:
  Pose_Seed=Axes(Pose_X,Pose_Y,Pose_P,Pose_Rot,Pose_Turns)
  Pose_Seeds+=[Pose_Seed+[int(Score(Pose_Seed)<0),(len(Pose_Seeds),0,0)]]
 Pose_Head=Header
 for Pose_Seed in Pose_Seeds:Pose_Head=Pose_Head or Bits(*Sample(Pose_Seed),Head,20)
 return(Pose_Bulls[0][3]if Pose_Bulls else 0,Pose_Seeds),Pose_Head or Header
Header,Done,Chunks,Count=b'',0,{},'?'
while Done<1:
 Name=0
 try:
  Name=input('file: ').strip()
  Width,Height,Pixels=Load(Name)
  Posed,Header=Pose()
  Found=len(Posed[1])
  for Block in Walk(*Posed)if Header else[]:Chunks[int.from_bytes(Block[:2])]=Block[2:]
  if Header:
   Size=int.from_bytes(Header[:2])
   Count=(Size+25)//26
   if sum(Have_I in Chunks for Have_I in range(Count))==Count:
    Data=b''.join(Chunks[Join_I]for Join_I in range(Count))[:Size]
    Done=Crc(Data)==int.from_bytes(Header[2:])
  print('%d@ %d/%s'%(Found,len(Chunks),Count))
 except:
  if not Name:break
  print('cannot read')
if Done:
 Bundle=d(int.from_bytes(Data),N2,open('b.py','rb').read())
 assert Crc(Bundle)==B2
 open('c.py','wb').write(Bundle)
"""

# (role, letter of record, long name), grouped by the typed text's top-level
# statements in their order; a group's module-scope role first.  The letters
# are those of the 2026-10-22 rename-and-rewrite search
# (changeset/RESULTS-2026-10-22.md section 9), then of the composite of
# the fresh-eyes arms and its search (section 17, rulings 53-54: ft's
# marks and the walk's shift gone with ft scoring through w in place);
# then of the progress line `9@ 500/557` and its search (section 18,
# ruling 56: fr, ft, be, ld respelled p, fr, ft, be; Accepted gone, Note
# now Found, the bullseye count); then of the grey padding and its search
# (section 20: cb moved before be and w before dd, ax's step_a c, cb's
# pgm_field t); changeset/reroll_template.py (reroll_template_comp.py,
# reroll_template_prog.py, reroll_template_pad.py) wrote TEMPLATE from the
# typed text by this table's scopes; then of the convergence of ruling 60
# (2026-10-23: five definitions moved, locals respelled, eight equivalent
# spellings), whose TEMPLATE changeset/reroll_template_cv.py wrote by
# matching the old template to the new text.
ROLE_TABLE = (
    # def cb
    ('Load', 'cb', 'load_frame'),
    ('Load_Name', 'c', 'file_name'),
    ('Load_Raw', 's', 'file_bytes'),
    ('Load_W', 'm', 'pgm_width'),
    ('Load_H', 'r', 'pgm_height'),
    ('Load_Field', 't', 'pgm_field'),
    # def fr
    ('Fit', 'fr', 'fit_centre'),
    ('Fit_Block', 's', 'fit_block'),
    ('Fit_Pitch', 'r', 'fit_pitch'),
    ('Fit_Dx', 'm', 'offset_x'),
    ('Fit_Dy', 'n', 'offset_y'),
    ('Fit_Step', 'y', 'step'),
    ('Fit_Best', 'k', 'fit_score'),
    ('Fit_Tie', 'k', 'fit_nearness'),
    ('Fit_Tx', 'r', 'try_x'),
    ('Fit_Ty', 't', 'try_y'),
    # def b
    ('Crc', 'b', 'crc32'),
    ('Crc_Data', 'c', 'crc_input'),
    ('Crc_Reg', 's', 'register'),
    ('Crc_Byte', 'i', 'crc_byte'),
    ('Crc_Shift', 'x', 'crc_shift'),
    # def p
    ('Spot', 'p', 'module_position'),
    ('Spot_Block', 's', 'placed_block'),
    ('Spot_Dx', 'x', 'module_dx'),
    ('Spot_Dy', 'y', 'module_dy'),
    # y = ...
    ('Rings', 'y', 'ring_modules'),
    ('Rings_Dx', 'x', 'ring_dx'),
    ('Rings_Dy', 'y', 'ring_dy'),
    ('Rings_I', 'i', 'ring_step'),
    # i = ...
    ('Cells', 'i', 'data_modules'),
    ('Cells_Dx', 'x', 'data_dx'),
    ('Cells_Dy', 'y', 'data_dy'),
    # ou = ...
    ('Head', 'ou', 'header_modules'),
    ('Head_Dx', 'x', 'header_dx'),
    ('Head_Dy', 'y', 'header_dy'),
    # u = ...
    ('Timing', 'u', 'timing_modules'),
    ('Timing_Dx', 'x', 'timing_dx'),
    ('Timing_Dy', 'y', 'timing_dy'),
    # def ax
    ('Axes', 'ax', 'seed_axes'),
    ('Axes_X', 'x', 'seed_x'),
    ('Axes_Y', 'y', 'seed_y'),
    ('Axes_P', 'p', 'seed_pitch'),
    ('Axes_R', 'r', 'rotation'),
    ('Axes_T', 't', 'quarter_turns'),
    ('Axes_Cos', 's', 'cosine'),
    ('Axes_A', 'sz', 'step_a'),
    ('Axes_B', 'z', 'step_b'),
    ('Axes_I', 'i', 'turn_index'),
    # def f
    ('Sample', 'f', 'sample_block'),
    ('Sample_Block', 's', 'sampled_block'),
    ('Sample_Grey', 'sz', 'block_grey'),
    ('Sample_Dx', 'x', 'cell_dx'),
    ('Sample_Dy', 'y', 'cell_dy'),
    ('Sample_Sorted', 'z', 'timing_sorted'),
    ('Sample_Tx', 'x', 'sorted_dx'),
    ('Sample_Ty', 'y', 'sorted_dy'),
    ('Sample_Tk', 'k', 'sorted_parity'),
    # def rb
    ('Grey', 'rb', 'grey_at'),
    ('Grey_X', 's', 'at_x'),
    ('Grey_Y', 'r', 'at_y'),
    ('Grey_Fx', 'q', 'frac_x'),
    ('Grey_Fy', 'c', 'frac_y'),
    ('Grey_I', 'i', 'pixel_index'),
    # def w
    ('Score', 'w', 'timing_score'),
    ('Score_Seed', 's', 'scored_seed'),
    ('Score_Dx', 'x', 'score_dx'),
    ('Score_Dy', 'y', 'score_dy'),
    ('Score_K', 'k', 'score_parity'),
    # def dd
    ('Bulls', 'dd', 'find_bullseyes'),
    ('Bulls_Bits', 'c', 'frame_bits'),
    ('Bulls_Found', 's', 'found'),
    ('Bulls_Row', 'i', 'pixel_row'),
    ('Bulls_C4', 'k', 'row_centre_x4'),
    ('Bulls_Span', 'x', 'row_span_x2'),
    ('Bulls_Col', 'sz', 'centre_column'),
    ('Bulls_Near', 's', 'known_bullseye'),
    ('Bulls_Top', 'q', 'window_top'),
    ('Bulls_End', 'a', 'window_end'),
    ('Bulls_Miss', 'm', 'column_miss'),
    ('Bulls_R4', 'r', 'column_centre_x4'),
    ('Bulls_CSpan', 't', 'column_span_x2'),
    ('Bulls_Cr', 'r', 'cand_centre_x4'),
    ('Bulls_Ct', 't', 'cand_span_x2'),
    ('Bulls_X', 'sz', 'centre_x'),
    ('Bulls_Y', 'z', 'centre_y'),
    ('Bulls_P', 'p', 'pitch'),
    ('Bulls_Hits', 'n', 'ring_hits'),
    ('Bulls_Rx', 'x', 'check_dx'),
    ('Bulls_Ry', 'y', 'check_dy'),
    ('Bulls_Rk', 'k', 'check_ink'),
    # def v
    ('Walk', 'v', 'walk_blocks'),
    ('Walk_Pitch', 'r', 'walk_pitch'),
    ('Walk_Queue', 't', 'queue'),
    ('Walk_Seen', 'z', 'seen_cells'),
    ('Walk_Placed', 'p', 'placed'),
    ('Walk_Cell', 'a', 'cell_size'),
    ('Walk_Got', 'sz', 'accepted_blocks'),
    ('Walk_Block', 's', 'current'),
    ('Walk_Cx', 'n', 'cell_x'),
    ('Walk_Cy', 'k', 'cell_y'),
    ('Walk_Seed', 'q', 'seed_number'),
    ('Walk_Row', 'c', 'block_row'),
    ('Walk_Col', 'i', 'block_column'),
    ('Walk_Axis', 'x', 'axis'),
    ('Walk_Along', 'y', 'along'),
    ('Walk_Sign', 'm', 'sign'),
    ('Walk_Nbr', 'g', 'neighbour'),
    ('Walk_Read', 'n', 'block_read'),
    ('Walk_Dir', 'x', 'direction'),
    ('Walk_Sgn', 'y', 'direction_sign'),
    # def sp
    ('Combs', 'sp', 'find_combs'),
    ('Combs_Line', 's', 'bit_line'),
    ('Combs_Edges', 'z', 'run_starts'),
    ('Combs_Bit', 'sz', 'run_bit'),
    ('Combs_At', 'n', 'edge_at'),
    ('Combs_Run', 'i', 'ink_run'),
    ('Combs_First', 'r', 'first_centre_x2'),
    ('Combs_Span', 't', 'span_x2'),
    ('Combs_K', 'y', 'inner_offset'),
    # def ft
    ('Read', 'ft', 'read_data_block'),
    ('Read_Block', 's', 'data_block'),
    ('Read_Grey', 'z', 'data_grey'),
    ('Read_Thr', 't', 'data_threshold'),
    ('Read_Dx', 'x', 'ink_dx'),
    ('Read_Dy', 'y', 'ink_dy'),
    # def a
    ('Bits', 'a', 'read_checked'),
    ('Bits_Grey', 'z', 'grey_of'),
    ('Bits_Thr', 'x', 'threshold'),
    ('Bits_Mods', 'y', 'modules'),
    ('Bits_Check', 'r', 'check_bits'),
    ('Bits_N', 'm', 'module_count'),
    ('Bits_Read', 'i', 'plain_read'),
    ('Bits_Dx', 'i', 'read_dx'),
    ('Bits_Dy', 'k', 'read_dy'),
    ('Bits_Flip', 't', 'flip'),
    ('Bits_K', 't', 'flip_bit'),
    ('Bits_Cand', 's', 'candidate'),
    # def be
    ('Pose', 'be', 'pose_frame'),
    ('Pose_Bulls', 'c', 'bullseyes'),
    ('Pose_Thr', 't', 'binarise_threshold'),
    ('Pose_G', 'x', 'grey_level'),
    ('Pose_Best', 'k', 'pose_score'),
    ('Pose_Tie', 'k', 'pose_nearness'),
    ('Pose_Rot', 'm', 'frame_rotation'),
    ('Pose_Turns', 'n', 'frame_turns'),
    ('Pose_Ck', 'k', 'cand_hits'),
    ('Pose_Cx', 'x', 'cand_x'),
    ('Pose_Cy', 'y', 'cand_y'),
    ('Pose_Cp', 'p', 'cand_pitch'),
    ('Pose_Tr', 'r', 'try_rotation'),
    ('Pose_Tt', 't', 'try_turns'),
    ('Pose_Seeds', 'r', 'seeds'),
    ('Pose_Hits', 'k', 'hits'),
    ('Pose_X', 'x', 'bull_x'),
    ('Pose_Y', 'y', 'bull_y'),
    ('Pose_P', 'p', 'bull_pitch'),
    ('Pose_Seed', 's', 'seed'),
    ('Pose_Head', 't', 'header_read'),
    # the session (module scope): the frame globals, the chunk pool, the main loop
    ('Header', 'e', 'header'),
    ('Done', 'n', 'done'),
    ('Chunks', 's', 'chunks'),
    ('Count', 't', 'chunk_count'),
    ('Name', 'r', 'frame_name'),
    ('Width', 'h', 'frame_width'),
    ('Height', 'j', 'frame_height'),
    ('Pixels', 'z', 'frame_pixels'),
    ('Posed', 'c', 'posed'),
    ('Found', 'm', 'bullseyes_found'),
    ('Block', 'x', 'block'),
    ('Size', 'sz', 'data_length'),
    ('Have_I', 'x', 'held_index'),
    ('Data', 'g', 'data'),
    ('Join_I', 'x', 'chunk_index'),
    ('Bundle', 'o', 'bundle'),
)
LETTERS = {r: c for r, c, _ in ROLE_TABLE}
LONG_NAMES = {r: n for r, _, n in ROLE_TABLE}
ROLES = tuple(LETTERS)
assert len(ROLES) == len(ROLE_TABLE), 'a role listed twice'


# ---- texts -------------------------------------------------------------------

def region(src):
    """The text between the line BEGIN and the line END (make_typed's region)."""
    return src.split(BEGIN + '\n', 1)[1].split(END, 1)[0]


def typed_region(path=READER):
    """reader_lite_v1.py's region, read as bytes (so a changed line end cannot
    pass unseen)."""
    return region(open(path, 'rb').read().decode('ascii'))


def drop_shared(text):
    """The text without its shared block (the marker lines included), as
    make_typed.drop_shared and count_reader.typed_text drop it."""
    out, inside = [], False
    for line in text.splitlines(keepends=True):
        bare = line.rstrip('\r\n')
        if bare == SHARED_BEGIN:
            assert not inside, 'nested shared block'
            inside = True
        elif bare == SHARED_END:
            assert inside, 'end of a shared block that never began'
            inside = False
        elif not inside:
            out.append(line)
    assert not inside, 'shared block never ends'
    return ''.join(out)


def shared_block(text):
    """The shared block's lines, the two markers included, verbatim."""
    lines = text.splitlines(keepends=True)
    a = [i for i, s in enumerate(lines) if s.rstrip('\r\n') == SHARED_BEGIN]
    b = [i for i, s in enumerate(lines) if s.rstrip('\r\n') == SHARED_END]
    assert len(a) == len(b) == 1 and a[0] < b[0], 'one shared block expected'
    return ''.join(lines[a[0]:b[0] + 1])


def rename(text, names):
    """Replace every NAME token that is a key of names by its value: word
    boundaries are the tokenizer's, strings and comments are not touched."""
    toks = [t for t in tokenize.generate_tokens(io.StringIO(text).readline)
            if t.type == tokenize.NAME and t.string in names]
    lines = text.split('\n')
    for t in reversed(toks):
        (row, c0), (_, c1) = t.start, t.end
        lines[row - 1] = lines[row - 1][:c0] + names[t.string] + lines[row - 1][c1:]
    return '\n'.join(lines)


def typed_text():
    """rename(TEMPLATE, LETTERS): the text that must be reader_lite_v1.py's region."""
    return rename(TEMPLATE, LETTERS)


# ---- the binding structure ---------------------------------------------------

COMPS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
REFUSED = (ast.Lambda, ast.ClassDef, ast.Global, ast.Nonlocal, ast.NamedExpr, ast.Import,
           ast.ImportFrom, ast.With, ast.AsyncFunctionDef, ast.AsyncFor, ast.AsyncWith,
           ast.Delete, ast.Match)


def bindings(src):
    """Python's binding structure of a program in the reader's subset: the
    module, functions (plain positional parameters, no defaults, no
    decorators) and comprehensions (each its own scope, its first iterable
    evaluated in the enclosing one); every other construct that binds or
    scopes a name is refused.  Scopes are labelled by position ('m', 'm.f3',
    'm.f3.c2', ...), so two programs that differ only in their names get the
    same labels.  -> (occurrences, bound, nodes): occurrences = [(name, ctx,
    scope, home)] in traversal order, ctx 'def', 'arg', 'Store' or 'Load',
    home the label of the scope the name resolves to (None: free, a builtin
    or undefined); bound = {label: names bound there}; nodes = {label: the
    scope's ast node}."""
    tree = ast.parse(src)
    bound, nodes, parent, count, occ = {'m': set()}, {'m': tree}, {'m': None}, {}, []

    def label(of, kind, node):
        count[of, kind] = count.get((of, kind), 0) + 1
        new = f'{of}.{kind}{count[of, kind]}'
        bound[new], nodes[new], parent[new] = set(), node, of
        return new

    def visit(node, at):
        if isinstance(node, REFUSED) or (isinstance(node, ast.ExceptHandler) and node.name):
            raise ValueError(f'outside the analysed subset: {type(node).__name__} '
                             f'at line {getattr(node, "lineno", "?")}')
        if isinstance(node, ast.FunctionDef):
            a = node.args
            if (a.defaults or a.kw_defaults or a.kwonlyargs or a.vararg or a.kwarg
                    or a.posonlyargs or node.decorator_list or node.returns):
                raise ValueError(f'function {node.name}: only plain positional parameters')
            bound[at].add(node.name)
            occ.append((node.name, 'def', at))
            f = label(at, 'f', node)
            for p in a.args:
                bound[f].add(p.arg)
                occ.append((p.arg, 'arg', f))
            for s in node.body:
                visit(s, f)
            return
        if isinstance(node, COMPS):
            visit(node.generators[0].iter, at)
            c = label(at, 'c', node)
            for i, g in enumerate(node.generators):
                if g.is_async:
                    raise ValueError('async comprehension')
                if i:
                    visit(g.iter, c)
                visit(g.target, c)
                for cond in g.ifs:
                    visit(cond, c)
            for part in ((node.key, node.value) if isinstance(node, ast.DictComp) else (node.elt,)):
                visit(part, c)
            return
        if isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Store):
                bound[at].add(node.id)
            occ.append((node.id, type(node.ctx).__name__, at))
            return
        for child in ast.iter_child_nodes(node):
            visit(child, at)

    for s in tree.body:
        visit(s, 'm')

    def resolve(name, at):
        while at is not None:
            if name in bound[at]:
                return at
            at = parent[at]
        return None

    return [(n, ctx, at, resolve(n, at)) for n, ctx, at in occ], bound, nodes


def check_bindings(template=TEMPLATE, letters=LETTERS, typed=None):
    """The roles are the typed program's bindings.  typed: the typed text
    (default: reader_lite_v1.py's region); both texts without the shared
    block.  -> a list of problems (empty: proved)."""
    typed = drop_shared(typed_region() if typed is None else typed)
    occ_t, _, _ = bindings(typed)
    occ_r, bound_r, _ = bindings(drop_shared(template))
    problems = []
    if len(occ_t) != len(occ_r):
        return [f'the two texts differ in structure ({len(occ_t)} and {len(occ_r)} names)']
    home = {}
    for at, names in bound_r.items():
        for n in names:
            if n in letters:
                home.setdefault(n, set()).add(at)
            else:
                problems.append(f'{n} is bound in scope {at} but is not a role')
    for r, ats in sorted(home.items()):
        if len(ats) != 1:
            problems.append(f'role {r} is bound in more than one scope: {sorted(ats)}')
    for (nt, ct, at_t, ht), (nr, cr, at_r, hr) in zip(occ_t, occ_r):
        where = f'{nr} ({ct} in scope {at_r})'
        if (ct, at_t) != (cr, at_r):
            problems.append(f'{where}: the texts differ in structure here')
        elif nr in letters:
            if letters[nr] != nt:
                problems.append(f'{where}: the typed text has {nt}, the letter of record is {letters[nr]}')
            elif hr != ht:
                problems.append(f'{where}: the role resolves to scope {hr}, the letter {nt} to {ht}')
        elif nr != nt:
            problems.append(f'{where}: the typed text has {nt}')
        elif ht is not None or (nt not in FREE and not hasattr(builtins, nt)):
            problems.append(f'{where}: a name the reader binds that is not a role')
    for r in sorted(set(letters) - set(home)):
        problems.append(f'role {r} is never bound in the template')
    return problems


def splits(template=TEMPLATE, letters=LETTERS):
    """The letters that serve two or more roles within one scope ->
    [(scope label, letter, roles)], in label order."""
    _, bound, _ = bindings(drop_shared(template))
    out = []
    for at in sorted(bound):
        by = {}
        for n in bound[at]:
            if n in letters:
                by.setdefault(letters[n], []).append(n)
        out += [(at, c, tuple(sorted(rs))) for c, rs in sorted(by.items()) if len(rs) > 1]
    return out


def _flow(body, split, letters, params, at):
    """Reaching roles over one scope's statements: state = {letter: the roles
    whose store may be the last one (None: no store yet)} for the split
    letters; at every load of a split role, no other role of its letter may
    reach.  Loops run to a fixed point; an except handler may be entered from
    any statement boundary of its try body.  -> problems."""
    shared = sorted({letters[r] for r in split})
    state = {c: frozenset([None]) for c in shared}
    for p in params:
        if p in split:
            state[letters[p]] = frozenset([p])
    problems, loops = [], []

    def join(*states):
        states = [s for s in states if s is not None]
        if not states:
            return None
        return {c: frozenset().union(*(s[c] for s in states)) for c in shared}

    def loads(node, st):
        if st is None:
            return
        for n in ast.walk(node):
            if isinstance(n, ast.Name) and n.id in split and isinstance(n.ctx, ast.Load):
                other = st[letters[n.id]] - {n.id, None}
                msg = f'scope {at}, line {n.lineno}: a load of {n.id} can see a store of {sorted(other)}'
                if other and msg not in problems:
                    problems.append(msg)

    def store(t, st):
        if st is None:
            return None
        if isinstance(t, ast.Name):
            if t.id in split:
                st = dict(st)
                st[letters[t.id]] = frozenset([t.id])
            return st
        if isinstance(t, (ast.Tuple, ast.List)):
            for e in t.elts:
                st = store(e, st)
            return st
        if isinstance(t, ast.Starred):
            return store(t.value, st)
        loads(t, st)                        # a subscript or attribute target loads its parts
        return st

    def run(stmts, st, rec):
        for s in stmts:
            if st is None:
                return None
            if rec is not None:
                rec.append(st)
            st = stmt(s, st, rec)
        if rec is not None and st is not None:
            rec.append(st)
        return st

    def loop(target, test, body, st, rec):
        head = st
        while True:
            loops.append(([], []))
            if test is not None:
                loads(test, head)
            entry = store(target, head) if target is not None else head
            end = run(body, entry, rec)
            breaks, conts = loops.pop()
            new = join(head, end, *conts)
            if new == head:
                return join(head, *breaks)
            head = new

    def stmt(s, st, rec):
        if isinstance(s, ast.Assign):
            loads(s.value, st)
            for t in s.targets:
                st = store(t, st)
            return st
        if isinstance(s, ast.AugAssign):
            if isinstance(s.target, ast.Name):
                loads(ast.Name(id=s.target.id, ctx=ast.Load(), lineno=s.lineno), st)
            loads(s.value, st)
            return store(s.target, st)
        if isinstance(s, (ast.Expr, ast.Assert)):
            loads(s, st)
            return st
        if isinstance(s, ast.Return):
            loads(s, st)
            return None
        if isinstance(s, ast.If):
            loads(s.test, st)
            return join(run(s.body, st, rec), run(s.orelse, st, rec))
        if isinstance(s, ast.For):
            assert not s.orelse, 'for ... else'
            loads(s.iter, st)
            return loop(s.target, None, s.body, st, rec)
        if isinstance(s, ast.While):
            assert not s.orelse, 'while ... else'
            return loop(None, s.test, s.body, st, rec)
        if isinstance(s, ast.Try):
            assert not s.orelse and not s.finalbody, 'try ... else / finally'
            seen = []
            end = run(s.body, st, seen)
            entry = join(st, *seen)
            if rec is not None:
                rec += seen
            return join(end, *(run(h.body, entry, rec) for h in s.handlers))
        if isinstance(s, ast.Break):
            loops[-1][0].append(st)
            return None
        if isinstance(s, ast.Continue):
            loops[-1][1].append(st)
            return None
        if isinstance(s, (ast.FunctionDef, ast.Pass)):
            return st
        raise ValueError(f'statement outside the analysed subset: {type(s).__name__}')

    run(body, state, None)
    return problems


def check_splits(template=TEMPLATE, letters=LETTERS):
    """Every split letter (splits()) can be two variables: no load of one of
    its roles can see a store of another, and a module-level split letter is
    not read from inside a function (that read would depend on the moment of
    the call).  -> a list of problems (empty: proved)."""
    occ, _, nodes = bindings(drop_shared(template))
    problems, by_scope = [], {}
    for at, c, rs in splits(template, letters):
        by_scope.setdefault(at, set()).update(rs)
    for at, split in sorted(by_scope.items()):
        node = nodes[at]
        if isinstance(node, COMPS):
            problems.append(f'scope {at} is a comprehension and binds one letter in two roles')
            continue
        params = [p.arg for p in node.args.args] if isinstance(node, ast.FunctionDef) else []
        problems += _flow(node.body, split, letters, params, at)
        if at == 'm':
            for n, ctx, where, home in occ:
                if home == 'm' and where != 'm' and n in split:
                    problems.append(f'{n}: a module-level split role read inside scope {where}')
    return problems


def check_long_names(names=LONG_NAMES, template=TEMPLATE, letters=LETTERS):
    """The long names: one per role, all distinct, snake_case, none a
    keyword, a builtin, d, N2, B2, a method name of the text, a name of the
    shared block, a letter of record or a role.  -> problems."""
    problems = []
    if set(names) != set(letters):
        problems.append('LONG_NAMES and LETTERS name different roles')
    values = list(names.values())
    twice = sorted({v for v in values if values.count(v) > 1})
    if twice:
        problems.append(f'long names used twice: {twice}')
    attrs = {n.attr for n in ast.walk(ast.parse(template)) if isinstance(n, ast.Attribute)}
    shared = ast.parse(shared_block(template))
    shared_names = {n.id for n in ast.walk(shared) if isinstance(n, ast.Name)}
    shared_names |= {n.arg for n in ast.walk(shared) if isinstance(n, ast.arg)} | {'d'}
    for r, v in sorted(names.items()):
        why = ('not snake_case' if not re.fullmatch(r'[a-z][a-z0-9]*(_[a-z0-9]+)*', v) else
               'a keyword' if keyword.iskeyword(v) or keyword.issoftkeyword(v) else
               'a builtin' if hasattr(builtins, v) else
               'a free name of the text' if v in FREE else
               'a method name of the text' if v in attrs else
               'a name of the shared block' if v in shared_names else
               'a letter of record' if v in letters.values() else
               'a role' if v in letters else None)
        if why:
            problems.append(f'long name {v!r} of {r} is {why}')
    return problems
