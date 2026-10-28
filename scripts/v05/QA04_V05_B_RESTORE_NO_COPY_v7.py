#!/usr/bin/env python3
r"""QA04 V05: finish exact-builder CHECK B without another disk-intensive copy.

Uses the completed, hash-identical 753-file rebuild from v6. Attests actual
original/isolated inputs, rehomes the rebuilt canonical snapshot by an atomic
same-volume directory rename, reopens and validates all its Parquet/SQLite rows,
and independently restores SQLite into memory for a second complete SQL readback.

IMPORTANT scope: relocation is NOT a second physical copy of the snapshot;
this verifies reproducibility, moved-path readback and in-memory SQLite restore,
not recovery of every file from a standalone physical backup.

No NCBI calls, no new query, no edits to source or original corpus.
A partial v6 restore directory is left untouched. Original CHECK A is reused.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import types
import zlib

V6_SHA='ddbec9eb6ab4f2e9334c647100e37e1bbd5d1ce5fdb5ea36bddfd63ba27bbe02'
BUNDLE='c-pOf>3Z8plHh+m1zNQ;AZ>`JPO4GeltkH_l1LRv*;OsGF(8qYP$EGZ0Ckkt-?tC3Pq<IA5s?QH2PL_Cdgd#OKxSlQW@OwM_~|dzbre=7eo$q>gRy#!@0LMxE8O1R{<U4(H9pn$jFX*ZFn>0dv)SAam=Utc+Mj#XkVWw_WR|h;1ApPpjcB<Jr_5jvzQ+RiBZ}QyKe(-Ib)MX5Y)~&28h*5#yD{^!fR2q-=r2Q~4K3i^jvL4D0@_WU4L^8b0W^9xJpUG+MwP9t-qN^QPcEUs)Sb_xiqQ{!7|)$Yh8rT9u1AO;3&eI5VgNsi;r#;o`hl^UyHmFH=)=_4vEf2bZyk7U5W`D9_F-nz`7&S?V;H!r=xzyZ0>IvVq;dSfV=D&#31V0zF&D40b?*AqF@iys0d#pby4AkH!Vu<&gTY9E#d;dALt2d0G8B+m96q~~IfDgR-U39N?RDhdGNbevhFd;H#?|tXg~K~GpO=mQ_kaGc5iE_Rn7;8Cx~mlns{-W8jqh+lzpi~4sI_Gn|7mQWw!U12OQ-GKu@Kkf3*Y&jW~C1Qzb}4P*c00}{u{a&#`gdE*uU(2Ia@vk^QG%WUywc=pbzJ~+iPDqC(dQJciO-D-Feurte$1Jot>}lPPl|c%a8fht?lkS)b@5xb{<&h&wS=3-30cp4-4c+`-9{D5iNu5t*t8}q-Z^z!s5-=bK~@5=kyn#tp6JJd$|3xCG0Q~R_C|&>Bty<Y&Z7ykrvcAm95bo%dP2K`$A`EIbC{4A2E=IzXT{mAG8e-oHQ3G;n8U9S8A1-@!km5i`BEys5C2k#w=VejQEaib$;s(N8R2BW90_{P|17=v~HYru7+?BLN=u%QG(51`71!y2w42M4DVr3IDB(BW-xBKvIVDki(op=Y>o8hIEKFv1Q#r0Y8P$EN8#<t4I`$0N3r~K;zn$Lm&2Ma=X1aSdrDxZurx6XEyH6ocRi0ie;Uii@Zu?+`xDt#JXyE_5OydBxO1aBXe58)e#*a>5eJ3ztiid0pR!4)aE|WQu|Jo;;t)>w#GT%&*URZWQ?rV`&i$A*)z4?O6tTZhAmis16DT|_<`p=kj7cOqbGCq89^oT5GCCvK=}(-@R@)hLuKI(K1H@vRM+dd(-od2aY);tGWYTn}jmE)#(`83TO>cT|IH`H{X=A^Bbl~kDdfskrcW;k18jU0O=;&Z?zhQ2D9<;BnIs*=FIyq?U?H<+}waJuCy~D}=UUPbM*x29o4)#3Ht4(VM2Ya)_-MU*pn(ZDO!Q+Gd!`WVKw>FzH&)hn>?p~Zpa0iX%!K}9LLN|9dJ@R1G+QIHo4G{2-rbqR?BX56ye{xV`wfeNaJ2`09+3pn3KdkQ`?Kf-Y)_G@i`jG>358eGKOlvx;O`7}7hFd>8tk-MqzE_*f4)*q%unfEPgFW|<P1vmIO%4zD8eYB5+`Sr`O#rvccCUNh8H%Nwxs!wGWVbnS4*{84bGLc8zqeO&z4~NYn>AoY-T`30yWf}`9eUIHUUSBFkD5nyZ?`@J?98p<uNU1>hePui;=a4rXtL(v-T`ynX5(-+Iczp2`x9^9JM#7p59$q8+lMtd+?!5jtj1tV>W4=)&tv=M)^+!cgPOoT?z*+f{?Xw<W7=r$d55rlhr7FzTC;gLVY{viYwFGF`v<IcRCC!ulL4-*>3P!`YfQ|oU#~lZ-vzMRZsTCL2?DG(_4a1)!)xvWyvA<r@Th(OhimU}GHo90O%6QQo$Y&W?XWqW9D0o-SjWbp34G(Kb2{prIfMS^p}l)_baZ%ZsD~&0{x3uOa9@AahCS;H?Z#eh>%4mbf0ax(jQ#1HMHS!%U)L-)Et5-92RP3%^z;{Sl355W&hfR!<*lphlZ)=DbJpqo4ggo{$=shp?>PfL0=>k81&dwJjosu42v_KR*6%u3gU)&PH#=mN>2k61=d2W(|1ABjbr;90=x?oR75?^~zEsM8^OpXX$}+sI{%`oJ^(A^&HZADZEpKgY!IB|Q^rN^0e8;muGby)7(D*Zuoy3j27RYozV#crSVZ2<Gu+7%ibnZrxeAIcGvK8^v7O<fx;(((&w=|hAC-4wN_c{zD7puS<kPZB0<&HgZ<)u`nZZnt+HY}|KDtC6KUzr}0uCS^sLCGkY;lwN>hnev%_`ezO{psC0K(2299}7!!cQNtY)~td$P^n&P?7qYQl&y(r0+M%?^$M1om8cgVL?WKTlF<AknmmIdR$5N}5O|8VC1lPO55yL|v?Abl&OLjM>`}O877HR2G;TEYefu1=GG;{#D8mJr6#+3=@P93{Tz+qU3CwZ@6atWzC379m4oxw1<j$CbY_^07gxoN`jrgSEM-GU=Qkm2y+(!8{dR~C8dS5DA=5=q_KJPfAL8oK#x#EI(7Icg(+=B?$Z5dS_-T6I%wPqmMmX8P^;+U7ys~unu?EjwnCol1TD;p(J$tzcb)N_G1V!6toIQ;$cqTBn$>Gt6NudYXO{#@ugI7o>-t>9qzu|;!?EEI!y<lrxO1#%b~0@+wbLfRnp2T}<Jbff7Kw5(^;T!c138*9<RNxgCcI!VMr(7pmvk8y1L3sf2e*$xbe2+3j8hukS13es|69HLfGU7#H*{hXF6pn5I*C<1FB-JkCVs_zDhXCq!3(G*k?Y=}Va1JJ1qPbgNT{&0l@bspeC>oD>k81(@)M@*Xjg(semR36zkV|mim*nl?9x(8}wvU^FF3MzYnSE8Mioyz4mw*<X;1x?nllBIG&bU;^R00n#xb)v!-oN)NxX%MQR;8whiBL5aCQ+}{!DKZrlLMDzNmNcnq(?I?W)4(&#Jb^>y7Wh_4bS;Z{M2rP?#DF~<FWh)~m#i-hiGw9zli|RkNsoPRgYi>Z0gD22@PU=!7buJ3xRonY5D<ukHg_?9VsnT^D>rG0U&Zyj(tWNc9XmQq3ByPqMS869W!u)zR(b;XKd}Om2y(MQMyQbuBk^IB`oj)dfz~H?zGn1iIkPeP%mm|@ESK|=7_dwNOlQX8#Z7H2q#c-!U^2U4W;u7u1x#7-gpND};>=f3Q6+OT1nnIZUIRNEgDnB<!nj?72?adTRV?DPMMt+HPny60iMPUss+!6aG6gyj+89$um{CYncWHi}tUA83ZB50sOzj6)nZrv|Rs=JTZ7@$NWUo+Hl6ejnS!GMIFWVHnR3HEbs^||=+`kPX``dR##7{_Jab>dfG@1qa@gp*;U`b0)7LMAczMN`coYGSz2HT0n5#V2^r+OFp684CC_W-ZVz6)e-^tKh>8{1En2c#8hjLV7kO6bl@pooa&M~LF7!=Q0V!V1P^)eRR2`=~(!khyl!aw{XOH1x40p?&J2&ml88d|R2VgK07|am2)Pn1yYdNF%0NE_w;`q~%IB`Kmqo=$!Wlmu7NuG#V@AW~$)8YKhY(@R!SE4z5A8o|!O^8Sa2uUZ3tx_NKdN56wWq2R(xw95rXV)7{y$28s!9@0<;~=OeQiq|(<Bs`|kvC))_~09%MZLD=`N2d5q9s@ogB2wyYGu)p>*J%+Nju$B5@nWz1;H;f_;0PLJH8Z7n7IqhHfMky%5m1m=MTk#lb=IEv>arZ!F0;VS;buKrX&gDtx><q_~a*+Y!`T;<EhB+`|UZje1<O<dd-_m&Lm6E_5S~7i}KM5ZXvXdQP4LkUU0k#V0J0!<ZM~T*xg&&gwl<^i-Qv92v1!fFz+0ta&1QRKI1{L^It?mqK<~BbC5@$tGS80^^;GQkPg^b*nMF6ej8JuoGuy6{-+i6hZUmX;(>vaUM&IaxCk#pT^pPqKEkQjRXk@IVt1JAVTbvkE5digs1sgF*v8Hfa7QYu)<SYnXPP06e0w82K~erkhJf7KoiUmsitNRaGgNE|W$zG$576y1qY{vx-<GTUcu062i9JN?-1eLzyxrR6sh#P#%kxsJ^iab-T4J}Upx%$9FB$H3?4+mlZ}_Xoegvy}WWJ+_Ku1N0JNCxMdLQn=9>FkAGGWeVKQmiXhl5ZR=_JCX2tmvC$gkB}pEB3t*(2%&-p*T$w*bGi&y>uBepX{L?=G|1a+@~LJNo%RP;*F$I6YhMjN0?~ooA9i~m#4-|E_RUiwun7cdtmeBaAKO{Dfj>k015H&hoI!{`Wt2drcRa!Q(`PqM@k<a_G$cQyS=`!}C*2R%{p+EIolWggfP-=Z1eIb_@Tx+3Noq*TR4aPc9RTy~!-2&EciQibI>3Y5XJ>=XaF`_~1Sd94&e$Q-A75C4U7-dmHfezbLiovD%B)nOVzv;PnZD~9#vj|mk6GnxVUv%5G(p}!rJkjZ(4qngPss%1VHx;SknO_Bl#@)fZK5?O#rK5`$;G9g4Xu+Otk&^H@Y<9}@D0r(G-u)RPZl_<h3`cUch_iAULTEfVAMQ@oeM5&wIPHy&^?3g?T&sg918`YHiovJ8X(DUNQRL%Pyk6f6!73{5H(q-;Av__0icac8RuEZmT^h+{g8l?ZW$r6p~F{K9|{jgw+EcA)58_K_#JvWBfvks$`X^|s6D#QY$&L+YI#^lUW#Q9nbx=OWqNv#<9IB1Hi_4e`Kh@z%la_<@d=R4S$j~tnT2DR<nM%Wz-s#gSiuekjnJK{Ph!yi?3`ZUT9&h{Ny0{tZOlR6fGVt?2kzh1k!=rv;=27FCv&CooQN>(8m&Gu>K;Q-z8nnJloWeGj$phu(06AU<h%2OTiYaWpDA21KN<Z%T8$Q%lju=nHu_x9zy;$nj*N?Q^!c0)F3u~)6{vnJd|*`y20klwN&t&|&;{L)d##Rz+lf1!Pz{S8ml(;7VUrd+ii;@RB94;)VwX7gQ*2Kjh7^C=;zqmh0B~1Uiv20CrI>e$#|w0UTuK=j?<cfw1y4itg{EY>#wvhGoVEub8b099{=m8D_BswwK8VFE=gl&2K3x>d7?I}zFQhmv9Ae8ONiP+90E>mUDPr)_`yiwb4(F&?z3#QmxN^DbAKAj+R9Yq8BXZ$}LXdNrtvPPW);)W+xr5tyYCXYzVU+U$fG;`diW@nrW#m6e`64y0)r)Ogn%gHqW)^){QwwfcxC-H9mb{l8_QWQv2l7+#`FRys(FIDpmU6z|XI$R6{WbIbLzbpEvApD^7tswAYRTH;Rtq%ANp0V7txUATbOk?t=Hfo_-$m>z?STuEE!C|o`*>g1eFyf;{01FbwSDiqnRp&?H0e()@j;QjRiSn8z4EjGrpBKN$$`-y`IhTx<+MMMJJ|(AzwX2X>m4{HIno^rWo0zSVsfD6dYv2)6G;)|bHYfKP>t1bCZ#|uRN_BmF}Y1Mt+Jdv^SVg&Ni_qIc?Cwg7%tI;aeW0c351^vez*&N{%ng#eW`p5{M4DC_t5_K{n+r9zO#G`z_!O<K-MAX`P|)W;F$!yj4<QRxMK;r01SLgofK}cG{{Bpp?Zd!Egzz<5oGydmGZv*>m+y#1KNcIcMK}8{W8%duBM3%y;E`kx<m7{E}K?lkBtx~g${;rQqH>3u(y))n%;$dxT>fc&`!Xve#Q6j4=3i!&It6oQJWl~!1#w9Fy?!w9aHx$3!^MeK{q7;vQsa=Yt(8j_!IvfzknYDbv07GHC%COCFDevKbC$%fZ6b!U|Ql34iHaN#yBma1Tk}~Gco`A7oq*qX~xZ;0GC8RF~Irl^1=}@yp)d2l>&In4`K*($aqvoIN{;n#WH5b+2{<N*_302%9XJWP#PH^p63{jM184}ASE+NFv<!>f_j0?BYTb*!{Z9b1CN5OA>x15KOOyk)%h~H`RC8$cR!m}II$cGKIf*3$CqH0|B9w0PVe&iV$^j2Pcs$ip;l=JF|@HAJr=GFj@fVv=Cyg$e#l~>rW)Hj)oSnJvRZ}SB4tiAvW$8Z8~^17YZvo~8nrLp7q48cc6!^!HbvN5)v6bJUn;?T0sryuzEp0P57l5g@vAEuuDV>u;!meU-D~w){YwRUZU1bhV=$f#7*uBK`JBQPd>PO}z73b_RjFJq3YdC&u#QfPC)(G`H;vZVw&m}JpcWVeC?@f2rl8{Sp4_z5(7=E~;AG?X@KilS(N%6G=LD4nyECd_@(+e~g4?2FPMS;X-lC&BvlS-CY|!tIic!P#2jq#Ix!#OZfjr;BG%`?S*9#V+?w~1F85|fQKssj{2S9-TJ^_naJ`?LT=$!TkXU;ERNM#lalts@bBip3#X=-*lB!kT(W|)5fb49Bq6A&-)<3bjMS*c>jv*mP+8B<kc3|z~j!Q^NJFWn8u77d6~pQo#do`p2C%Fzs-SVec{O?~HRd{cw}yfZBj@LFrWB*d;T2GJgw8%7YU3O9~MP)~F*sX@yMVtwatR%5$_^SAsmCjk{wEFbIeD6$F9xD>y^F5~xhJr^U@mNFl;#CS<$^TkE$cRRBsVpF@`1<W-0b@TVGH+o(%u!fgDI+5R}KqN$Q1~YmykQ8>f>u<uB5B5U?rLoNtljv9NT!<8d?%B=XJ1^l1!oy#{Q8k4`d_o;RBw{U>E662)qb2T1n#4H0^STz5(AR@I2Th6s;i)&2=YxY%jGac$ua!(^!q>$Ca>0mIYE>m#gQaC!)J5VAYR+SlyO0^c<4iNcRF9HbuT@O0iknrFPK46S-Qc-2y#wVuTA}N`EK-%IQMo0k*~^bXWFQv;W9aE+OY}`TH*m^C+j4HbD8Jh)UMK!e>bqRB$X_?!_%HUV#r5A8(bT)xt0G}9HF;fc=L?3rFW>66f#S<jdm`Nzv_72~Nwxh3w7Rj4TqLIpN)4PhL2WbNL@MOG4QhEZ;S1kr1dwR!yeYoEF)>%&$0)3W@6D9cJY_G~y2-+|!}CG^ADtfOj>+7l=YrcQ_BSO|TDwO_^@b(5+Ts3pzDnoq%kIVR4!v{^_w&v%zKO8Jhsu0Xn+8vJ4;lwYmWc;K*iD1Zuzzt)uCYUhUT0%B967Uv`ON}T477+HF<bI43pt0w5ikWc@n?d7&6f5f6Uz~s7n!Z>ep;s7HT|W0W|_%WnXTk+%UlOOsP}wB%oZ+$zC~qe*a{PA?PER={%MJLrcgQ7Hh)|-Iizah*{<RkU?s&*aVm(gF0k6y8LM581G>-)%=U@B&im%{sIMMl*FY7djBtYF@n+3tsYI)}AEQ*rfY%Rk-W(U?Ej&HRktRo#AH?aI4KWLxEI3K;U)5@2q`+tTdgj(qc_qH;Ne5~KEhmA;Un1RTEy;m0VX+rtGLbL~*MS4X`sVZrfsV|&*eXsbk<dXn+`G5TL9I4%JAx!iGHVvmO<}V!ptQfM29yUF)a>+;<;vJ1N?bRXpsWSS$b|#P%UW2x?dq$b_MeP%P#k%}OLEo600w64{A^rtNciXQ*9*`93{(bqexk=7*nEk%M!-f|tz+R9_a?TuZ~$gp5HMsRCT?u&8+X%gr`@#Mx?k%1-xip%6E00_9r`@MY%7;wCrzgbUf`Lo!D2A42JH`*ZMuze8~X9HL-A+Wd<q7E;#(?%<pUcG%vHI3yS-88!ys*Q%dBt*=J73rKCSSk-Wrp*C2zMrDko%Gek+OW2@pV17O+2yN8%`?V5ty>1Jg5LTQAjsX8C)Oc-8PJJfC<X(`~dfDkrLoqSOAT4lI_gr-KHw<}=nVw%}PWrxPwMYG|#N6u)_SF<>8-;WN^lBiqw-$$PP;CE&xF#g-m9B(;gDx%3BDAKP&7hQsTut)b=tiW6xyr4+(>XGOGLlosv^7ur&tc`h3A3XF#D9wg*~L#Dz>WJI!OCtiv;q3|VYS)?$8<J$P&i2lp$+A(@5H5Vm}to<U9N+Cdpa%r@8solWaRf!9JaifRF#+fj}4R^c&KWSyMNx#BbdsMHFH#oiZC6oS3>?JjVu@-ns?0>G;W%kI8A}}MAzc>SjbT6<GMW~GOQX`I{WNMN%79$6Qlj<wZ1Ks&3r^ACFO-9Zyo!^JWCNK@EIW&QJ5VA^d;mC6H8{0|+MQ@xaGQ4#r-ieOStlN-8IBcazV9<6on{kgZ7wKBoDMMz3;y%&D^Y+2aMz~ekGH*W!d0e2^%w9+-p22db*Z)Qi0aKT2F1);mnpt3h;k1%&_UbDa;FQA)BUIq9t)9tInV~G#=6&-wd&b9b#Kg-DcYMajjL9a2w|xo;jySX{te;4lK?#kc7aVCriUc~*rnVNq$J2QjYBs=^Pymq<YJwC>B#`TVKaS*UF`a;ida_NU==(;r0fNNWO;nL6c?|POL=1n7e~K2#B$L@lTPJs<K!yCaY9SC{%{OL|tTe|-AS!{KMn4Lt0#qbHrMB~pU<w-KkBDmvbdP~?i@&@H%Jd0Jb#Fof-J8%^)dUr^+jN}VO*6M`giMPKZO9#ikKm7Nnn=o1Kq%NLs}@XJZt8QqfSo4{r1~xRUM;xwrp_f7bC@`B$_<pu0tQ~>B}93bp@Ko@s)OFeV|8O;m50N9g5Hx|BnFBWl42pAP3kiK1<Z-f!A9G-<h&Ug@<boPvW3;9p_60CeZ<1petqT%AK}|)@(=+}{-&!8Q4wjDQ}0od;C9R~5s_YNdm$62-hzWp{9;E^T8RpoifQWZ+M)qcooVliXY&GPX~zj!=t?MR_Pdmd$v%t*-Oi`>g){12f|P7uUKQXc^f@4IfL9e!(4W3-=N$LjiMMzg{VLns@xGmk9c+KMzX1(q)SdKnWUh|7%jvA#XEZyda*LA_f95vvs*i@opkN|@5<@L1ZCNU++><Dt@(WI!jD^a)dFgc(*tY-79d6QLhm=~AwgEP|*9Bbj>iXnTBpwPfGK&ziOlrYZWlUeY8gz!8-l$+CQglIjNKYuyhVDEn<NzXOPiII#F#gj}eT6fsV1W_`9nX3;#kdX^0>B_C2qd10h|dCyA%6v2I@2_ww$j&zg8t{a=)y5@CM<qrGKG>_^B1C3fJXj$wVM0LHH2GR&WAS<abC}SjkjSp&8!mngJaz%NsqW&l01QwC@7WSO?#soAvYOVxv)%H%n1=z3NT(kab&qpWpPn4wHJ0WSw49TRh1KbfgxOXUO;#5Pi+|0rGgj^{9-}GK&8WML>qqIh>O=0`f&6d#f^f4dI^AZNt(0yYyu;f+4Fe`f!^GY^U0JYQ@j6-EFWVi@TbQ@A192-1R}E%l|lHo(;F6@Opsm05iu1<#WPrRC|mHy4gJXVWzrDK2N!rywjf}Iwq=QJ(q$}ogPJ=9MfguLsGVRLF5ndX$wZ?c5GXLB6l^S|aCUwJ#)@@PwD99GHsN<9+4Dw_X)O6hA=O%3;pUPWC%Ft}ysi!sK)q5c82r53xj4(}yo$z|cgvy;Yy7Gfnua2r8eRmPQ6OrqEUp#9qvCj$(z@wTrtSv62%c6W-Ff3sa#4|*>@?7V^}^fWdFex*lK0XeA;(GdUK%3wlkuO76*+Po*A{M;LN6H$(w;Gi)Q5}y37}Nu6;qL#SHd(Bl+Yft4kGETB%d1h*1%a*DU)TDnYs=n7nE7&bY=wyHg)#}m#=5tQw-xIx!4)k77nAFS;Chkku7#+72ui^1qGOABv1jun$*deyV@SIpR>t+IpWEptfE%Rk=i0^kk^dF?<ifwgFj?^AK@1=SH7oXD|d*J&8KGa7n~8nVOzP?wv@k$k}AzsHqq~0vtS&t?c7RnWH|t{wZUmoO&LLzw2e~$Ub1OSDhEw=F=1hJ=dS?15JnDW0676qkxTRE%}^Jhr-nY~?2dMGg3Uo^p7?V=##?*s6I27S283`%f2!@h3XMHY=W7(y7|MufB?{q)^h%$KP_?{Cg$k2t$-^RTIJxdcQIUnZqy1oKa=Y<;Izit4mbRs(m$dp#`l`O0Z_My4_R@V%4JY%cOT|~1tXyutl}mq52NB_%!t}H||LUGsxAzH_6fa{P>@~?PH`Gdr2tRYi!JMfW0`stV#x~D!FYwn&wo&Nq2h48L%Zo6!$sMpg7VFH{7(F92lEOc6>UOwSQ40|Y?f~!wEliiIXJx#RYZGJ|R`iPEq=rCuu~_q(0X(@1jyL_n&b$POtQHW%Hb+SEq~62o@4%_O=QZv`QIQ@M8kpW8Jw)ijI_9@J;3Ps{7y+=ugvU9H8R6jvbnFc*iNosy#&>=sDOE6qig6vtoitV<+hI>WcD+r3pekg5+|2dokto-fE+it!Bb*ladd1Tuifx#`wjHX1CvsMkJoI!Nl*}2V&X>EN(ajHDA4US0@s2c~6un5{B)}Hkas-5d!qrdORX!@1q1TrkP98;9Jv3rTa+7E%e!sD@xW_x4{D-IkWDt(d@?Hy6;&H%|B8yd=aDiQI7E@ql$WGE3P`LskL}j@C>B2}MCspzENj!bbD~@uQTz-*6azccfsi|ayxuQx2RaGkVK|b=kQzZgbs1UwkV|ty>FYk)BGpWglaw8{h#8lxbTnu>L%4Q6T)yPjHx9&+kG_3MEAi@>3ebO79*3t<TQTU`7AQjZoAN*ttkV`05A{dDA;4kN*3=nKn!eA1!m5%co*pih2I9bP{u8HSI_dA#pYVkrwAZu>pI}0I7o<MipkoC}3fraBUEm52=ju_k4^BQ2XmYga-ex=-mK`Vqq5c0O>qaRRRP}AauJy~0OR<mI>n`J=hmG00tSf={cn^t|lT+WriNfwLDa&Zj*YBUu`+rV1%EU-#6XKYofRT_K7JEQULoq&_y_QC{2Dzdhv{xaIqXG9CewR{((!2~murBI>*pLl=F!QA~sBw4CPDqSqpD_?<30`bIaH}LyTcpng9ScWY2it-9cO7nPB6Yr~#PgKiO)DMV6WyuQm6tM0<XvoJj2dwuhiFV;W8}2P&cnjxii>I>&J3_u1((}Our=(h=gcll@6CNfMWpN*xMiehsnKD<&y*gwdZxt{X{a&GHq4ouQynu}-0~4#-6456|TsBMJu0q@ra~_%Y#tVL91&O>5_P3Rm{gQ&=h}&4iJ3<CrVI5_))C9M50Gt|^|7xpoQZf)ssX?3Tc^UUCY?BW%qqdc#=EFSG$@wx9Ok$Y5v8dfoET`%V6>45pfN$Y6@Q+-XD8xqhSot$`9&#!0B_A~F|7h&hY`c~zSx2`TXC{@_<+ry_1d&_~`X8|5fI(L*U^fKx?*`=$q1F#zLH8s#gq(8uyJ^k9FuBtRMiY3t8KJ~pcGq-LJ-@!Vc<KHrUx*a1Q1|kPOYmaCI*WMmln^b@b?blspum=hQpUPti9bT`8SHtqo?xwPbf9JKXPT1gGK8`DE+?mz!dF`LL+;MQTXI(FMqHX8e*o_!2AgHogsR8U@+`%zy)<iA!9tF(Ogzn)9jC}8$u{8i7i7tC*^S?VjksARtBNyG^$?5)RrgSJlr$$;J*E1IcWyYn^Z7M07gPFFL2;0qNvR(m!s0rFw<i5WmgeEc%@W<0>jl@o;ydW;tykRD4sBgbE#w1vMrX+IZz?Sg=&wK;F@BC2y4l_EInkhDWnvUs0U9+^Sxenm&P4G=Ve53xF})A3$))86XRf78Dkz*ek%U@JrJ%xdato@b)g;YVGlV%OB+!~VpXX{k4HX%ip*UMA!5SX4QmQaD$qgbCmU)2!QQU%ZdT~1}p~pq}6Hk>$awndbe=0P%sKZ8sOM)vhxJ1zuOhHii&}diPUQgDX5^^WQ+|svUXpqgORsrYPY&H?Bw1qTl&4jU{(0tL5$Vd<b_!eUzQT{g6{d;+#Ff;0`dw$*-aG5NM-YmT}2oUnk@hp#(6(rU5u)3e=(C#>n*`m6W0NNqRk59-u1HWa4F+4(MC;d%qT9WrI)7O422@2boWh;nMWE@0WTYt}#Ij2$r%W&d*j;Pfx=}AS<MN+WMYm`^SKjP_euARf4ikrfV3}CYHWMlqILV+C>qGk=&%#FAsjM!qduJq2e-o3kj)U9-E2<<@oI8K#KHhY~B)~0gWqfzJbYUG?;^iO|LX%vO1+BnGO*Eq#&iyZn%3#57D8C|{{%ard^O`sT&?CKtGM5tgNvas_wX7)lAZSpaX`Sw9qP^NR=mX-J`?eLcF=3UWMXJm=f(5G`~n_Vp{9Y5E>zjbh88S<M7>gxv~TSrW4vU4A!S&l0pm&~0Vam~ZDu+%+OqqRi7Ga+Ub=ULsc`N}r?EB=jxmMHw2t%Y}Nxa)X{LTf6%>49~U^sgqofS4=32JvrV26(OA<YN$EQQ`L>{w>VJ$1REwqhghz`IfI<NLO^x2%Be~EAd)2U;Q|StRiURP`rW#R?Z~qlgukZ;NMJvTxhn;7e4g?3M7`5hO^~p*CVKL68`?R4L~Fx$Xs(GJHo*Rm<@wWLsW0#FHXdZ&TpO5YyLtoPKQ4GVzz2U0O9$!?*M}b+URfb<rw~hJaQ<dRNMpy8IIb6Q69wzbQp#+;DI4LM%Yyp$Rqc?BfnPTw4H~h#-&A}Fcm8T>488*L}qn|_3})-iFwie@NtA!W-zhK+<2!WdX6fv-W2okgW2+?)x<oKro~-8mU;F2=wrXfQ;SG)YM#Q}aIl|eQoxG(t7hufJDT!YGP9^E)b!C4f0m?dEvx#+Wud7g*&{1kuV(I61Y59pHS-&D)E@p)tJRuBIj8Mjzt=qlQtO|eQ<Wo5cn{5YSh;t+;k+BEqQU8D(Sn>~WiAYjo%KKWF8b|MPJ(A=ixlgQZ#)z?lD5W}0*#w5nmVBJIT$YVJfVT2DMxkBURnG0>F63JCO;5jYS(Ns3+6hU6Q~u-9Ln|yEe|i~vuS}0{YxZR;uXe+!9O+S<5yRSoKgC%GB+%^Kc*|k*nvmE6-U8~WEu43M$<IRqO4vGkmMN%r?9$QQG31K8ajUIHl+%}@uF9F`wtD;e;Kei=NRulB&w+I9;kaf|0+<$Oz3I_A3+2?*8z{4d2fa;&HZ(Z4u6x1A5f^}O>2Il%I+zK{7OG^Y&%5#T6Mq^r#tLlw5hx>I$83OZa693{=iYi1Yv3-U$XzH(=+pDQ}TB>oHV>6s6?Eb<mQPoIoxo=2?x^3o!>kQ;G=9JB?TfmT?N3nd>YGOw!Yr{6;i<q44jH(^QG+eduA>ac*ASPj?*PqJ(*lq@Iuw4O<v{qra$O@pks^U4>MPFb)&;hFes{xuW8J5J4{FH#r6_QJB{&+eZIQ3TlwnJ1=7^#6^cJXkjw>!aVwmPex#q~Z~zd>eLxG14}>wVR@oFh7?h9?l+e>1j)r&<=&Ft8Zow*RBYbrcknVJsTaZMn^KJNImy3>YaR<592~asqw&hoMBUq6)U)+J$uMoo&w8;}AI%~184rZubw6Ac<ICYvE_u|#1Droe|S`}ma62R127J+ob*AdOPc?HjW2OZ7Tiz61nTWuKMG9*0%1xqDNaVqDeefAO|XMFLvy=kYMaLhq#<(5lAQZS<|%an42@-et1xx5~c0D?n>mk?0gBn*^FIA=;=tF=h6IY*UVw6jGRH*~-_Nl{7_U${gC<b{4^VL9M*vQ)R02)wX2mwd*G&*_nc*1&Pyl=GEK@YG6QrYB6d89`#Dgs;+8GOJ;Zi%2L3TrAGZpk=t=2Vp1Ee;ItzPJ(|y1fKj3CaWW=ybEFy)Mmb9L8#G4b9SgSmBV!kv?22vi2OX^dIBaH1_X*}{KVmEz5J4ZQWg?OcR(q20;j^29$uxObYtH7n18=>YLbIfu_?<8*~1Pw4dC_14xHezh0aYbXJzf6Ecwu2w&}8l=N;CY_1Wa$aJM#{PWERtcY4%pHoWPqS!Znb;9#HOB>?5|y}ay>iZWgj?S=~8YnqDei^cB?1SVR~+*==D(m|<4GgNSN>xD12{7k1C87p_gOPOs-jlO0Z@$Y)Vt6-In8&n)e8uJdU5&sw{zcUf6vM=$|pr$@U2L#>_nQ6fi@hTQl*%vIr&X;!a^3^JD%#70l9b9AE&H&p`kt2Un^2Ip{5l++aS$Fu0bK1UYpJMq5t>R;!B5;^mg6R<?buj!toBOwSv2h1y{a8BsWDW-M*&W#Wm@SO2>t*al8a&d*;yXrpKht#>QYsNY7%ak%Ss796&*$*h8f(&_IisZk<pL}-5J0xb2EimFXN_O(1(785y>bOxWP&1(oC#olerbi}wc-+<Cnxg%WJ%J4k|(^tX<2^mfNGqU%f&F?za3~Q60CshHF<UEh$7=nXw%mYHdl1c<grO(4pt5qN^nOvcGM=L371<!(GOEQF+<t|O(Yf;GnYdI2fC_-d8L0MYf^Is2<Zn~#W`+x;{Bxq<kH$aK{X|Zr*MsJnb^g<S~9hZ;sTqFO2(4b?42J76v86eUtN(nU>>svpMJ`3W}C-f(XB<#$iH<g;_LK8{GBsD@!r={MJ92JFE8NNLM2p-1G5watzsT3f}q3@U*Dkh^RTH_P-E1;axOZbIu}KfH=Ama&<454%}fddW{^lCu%MmA0p<8*R_TM^pk1UDCDLMfDzL~Y>7Jjb3fbb<rZY(mk>So!r+cPM#N>PE#Ibnlv&u=RZ0T8(_>F1GE>O7!%&6CD|Dol<QNr1T!D_27x*LznHT>80JPp`7P{{|1pW=7S$y<OqlypH%rmkTqR!@@Lxb`xi+biCIytYI+=Ga_(J)TZB@AU>(%?2-gl4p~HLF6vZ&xRvIm6MQ(+0?jd((LNoBP3MFhXy*VlcIe*HKd?Z5-g!Mpa7C{RA}-kAo+9$g^2~K4F9^1W+LR<YiL--W<@qSuSU>67n06&(10diDZzSldC#5}(NBLJNiC}rM0P%`pUl&g^Lc<p`s(seniK$$j<wDw{KSe-KkN-E&PK1fk#xWA<@F#@9&K#NPi*Pmdf5n5C~vl)fF0QG9Ug1h@m4$Pst5C`4|P3EA!725{3>ec9Y*jdK2IOhYZZs%r86JP+MaaJ&Qd;9xm<XSkwe9tE`5}QgbQ~@r>N}S$PZAJbr^DE<Y%wajywzWKD+@b*4n}u4B=S^O>7I5ds`{(g)2-nYA5uPT$-b+`NPaDx*`y{Z)4{^rjq%fcKT;(wnQTsxw7di@|B^F?5`*9*Orii=%Y*`Pn7bP@F9I9iZbuy7M0&-^>O!n$|sz5ai1X119I-6g|wAQ56UK}pe`eFyfdX#={lcH6Qo@>$ECdBO~-4;wgh#PuSCz`*)=^qJ)*jFH5sjv6YTYS|L6?*=v@*dzS)?N*S08s2+T@!s3vm`*rQYA?m<DWO$H|zJ6V5=>|E$`k)1a9TU1{KJjZ~uUK?8ji4J30jbwhCFYXk_FU8Sxga$x>$SZ}X`UUC8eJbgMVTla3G!k*9K%$UPAnh1LX+BA~NV`ow?<9ucMWF_r_Sp$=35~u%BM{4DCm-iPhM|3HL*EurJ}y-aQtb(8d<n#4kCFnBFRClNbwOY#Tt2Ee<EAKaPPGSBchnzr=x$i*M5EUHvYN74|K+_C8>vVG7K$%6%qhUHLKZ?coz0xU-;nexdRL{4R@Q>9FQ1A_I-sp$J~8t|kxh{cj$f5>Q9+IUU>buklxsy7KoSMDqy|eqS6Kcx*Hh8HxiKkPJNdcctEms{sf6hQ@NYaboN@}zOO)k!VhC-nS#}pj#f;7`;&0G6%(FCTYiHP+sIHo}qa-p}TdK&@i-x9BL^sk8Wf2Q-!p(dGkH&gpaV{l#Lq_xq3DE_{s@w$P&+<BPw=)#UtU9OW+{MvdbsHyC;Jph)J!0|s0Wt6y6(7zI7HW)Ao$?&F6m(a>Epdlsw-7d4bWSlxiCCKH+G(%~Q&Ih(0M{auQ1LIV)JouG`3|vM#CPIO?>C!^DiR=d(@Z?Tekq=?S<g4}VkZYplj?7SL^JmaLHXtKODbQXyb(D#GNjSH#MszL_afzc-Qe#~L9VwP)Z&m=`b@s1U*IYyOR@=X4$_=m5Ad6Lf?XC6StdzloVkqrLNG`4L@G>ZGRe}}NPKTfqLdjWqt59^o*(zQJNoEc_dwt447%-$?mu95oeP*W-#l4)CyzN+Y{DuOyy8<*RDu`OfPs4a(*vSri?{}NY=G+B{gfGmf~gt?`QftZmSeJMUQs7GKOl9I5}%~oweVPzLTTjvJm}`(?^0%nUCS$<!hxH<E1lRoRP_zbw-PH?<mCbRohog{I6)i3N{n3H`o&<28|7tDz)W*on(q<(R^~GvnXlHgcm6TP|I~Jlobk7&Rj<{)n-(9joOLr38t8WH3<em1M?#^`hr(C@m%jRO^G^v41e#-7h(r0NwYxWd!w&L4at-x-udz-4ZfGN`hGl1-S}}Q#y4Z`(0cD-%Y=hrC-&0+@PIXSMV{h*7FC8rH&W{gWj-(~Qmok4#R}U@N>|w4n8%%Zs&bHk+#JlL5v9j%Yy^+75t>H&C*j6En)tRQC8eOLB;}_=pqqdp({!SXB+>njh{tpiM8FbP9=OIs2yXf>jj6VL*n5nDq|KiyAb$6h9P=~v4)I?=vN2H^_h)iZnesFy5@K-6d<{Q3s^fJ7@ILy~QI>}w&?i$qW(fNeV6s-!uo45&QTpNy?bQi$M2|;V~fdle$1T>C;G3vV!AN`7aW`LiJZh#-|<waTK?R*dm4;Z=-0TEdch{`_Dg-dZ!EM1g=M`&$UL2u|yZOp%1hCjHOp`j$3SXeDvaOInE;ne9k3%<o`RP$16G+6nyE}U0#jz=*>Dj+87*5`{n(P<g=`#_|<4^;lr1Pk((DvIJN|9P`hAFHo45#o6uDYEB4KyvbWnm+)B4ogDB1c&OJ1Ka*FNd3`AQ0d9q`jhU=^Tm5f$H$TfNc!^f$SV@H+Z&Ds*OzGb!Z8t-DV)x4r=6?B7n-{YhBK1RMw$^87Mo*A*$=re0ZLi{PQ%)IwXBL#6YYOb$^M^ExPMsrE^p*zIc1u@{v+qQv0H(1{ZjtB)U0tI)Kftg=k4x=x#?SJs&R2ynjclraV*V};xS(l<a%*{yoO~KgOTRTuUYAx(O+BtgG<}L>S&RK;#<YVInv^qv1uh=iKh=<Tk?bO^Z{9Z1v!T>-81pli&crEZp{Epv<9P}KH9|1G7BqiIQQ&XWH|V=Id-F<LaeyroP1Hc$O2K9QVi6Te`NRH7i_R;wCx0rx?b?!G){8QPd0&&>im1;wHpbhT-;gM`0sV?RM*n6PTb|yMTcsg7lTOKPH8kUys=#9)PI>a_0<<i!=DFOjhob+<Tjnu1RmW;l)FXoPq#bg&zO6_Z&T(l5Ers*yr{*G>}cv!hs0lmsA+6%Z2>fC2imsjICzg2FOO@*jfRwU)_L;d65a9zVfX(5o7DcP'

def load_qalib():
    code=zlib.decompress(base64.b85decode(BUNDLE.encode('ascii')))
    if hashlib.sha256(code).hexdigest()!=V6_SHA:
        raise ValueError('PINNED_QA_LIBRARY_DIGEST_MISMATCH')
    mod=types.ModuleType('_qa04_v6_pinned')
    mod.__file__='<embedded QA04 v6>'
    mod.__package__=None
    exec(compile(code,mod.__file__,'exec'),mod.__dict__)
    return mod


def rehome_snapshot(src,dest,m):
    """Same-volume atomic directory move. If already done, verify and resume.

    No deletion, no extra copies, and never overwrites. Both present is an
    explicit fail-closed conflict rather than an implicit source choice.
    """
    if src.is_symlink() or dest.is_symlink() or dest.parent.is_symlink():
        raise m.QAStop('REHOME_SYMLINK')
    if src.exists() and dest.exists():
        raise m.QAStop('REHOME_AMBIGUOUS_BOTH_PRESENT')
    if dest.exists():
        m.safe_tree(dest)
        return 'ALREADY_MOVED'
    if not src.is_dir():
        raise m.QAStop('REBUILT_SNAPSHOT_NOT_FOUND')
    if not dest.parent.parent.parent.is_dir():
        raise m.QAStop('RESTORE_PARENT_MISSING')
    m.safe_tree(src)
    dest.parent.mkdir(parents=True,exist_ok=True)
    # os.rename does not merge or replace pre-existing directory on Windows.
    src.rename(dest)
    return 'MOVED'


def sqlite_memory_restore(path,expected_set,issues_expected=147):
    """Actual SQLite backup API to an independent in-memory DB, full row readback."""
    db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
    backup=sqlite3.connect(':memory:')
    try:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise ValueError('SOURCE_SQLITE_INTEGRITY')
        db.backup(backup)
        if backup.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
            raise ValueError('RESTORED_SQLITE_INTEGRITY')
        qa='SELECT pmid,canonical_article_id,doi,record_hash,partition_uri FROM articles ORDER BY pmid'
        a1=db.execute(qa).fetchall();a2=backup.execute(qa).fetchall()
        if a1!=a2 or len(a2)!=len(expected_set) or {r[0] for r in a2}!=expected_set:
            raise ValueError('SQLITE_MEMORY_RESTORE_ARTICLES_MISMATCH')
        qi='SELECT pmid,category,raw_pointer FROM resolution_issues ORDER BY pmid,category,raw_pointer'
        i1=db.execute(qi).fetchall();i2=backup.execute(qi).fetchall()
        if i1!=i2 or len(i2)!=issues_expected:
            raise ValueError('SQLITE_MEMORY_RESTORE_ISSUES_MISMATCH')
        return {'articles':len(a2),'resolution_issues':len(i2),'integrity_check':'ok'}
    finally:
        backup.close();db.close()


def main(argv=None):
    cli=argparse.ArgumentParser(description='Finish V05 QA B: no large file copy, independent readback')
    cli.add_argument('--qa-root',type=Path,default=Path(r'C:\Pro_Adherence\qa04-v05-B-verified'))
    cli.add_argument('--report',type=Path,default=Path.home()/'Downloads'/'QA04_V05_FINAL_B_restore_v7.json')
    args=cli.parse_args(argv)
    result={'verifier':'QA04_V05_FINAL_B_NOCOPY_RESTORE_v7',
            'check_A':'NOT_ATTESTED','check_B':'NOT_ATTESTED',
            'overall_independent_V05_canonical_QA':'BLOCKED','checks':{},
            'network_calls':0,'blocking_reason':'NOT_STARTED',
            'restore_method':'ATOMIC_SAME_VOLUME_REHOME_PLUS_SQLITE_MEMORY_BACKUP',
            'second_physical_snapshot_copy':'NOT_PERFORMED',
            'standalone_disk_backup_restore':'NOT_VERIFIED'}
    phase='START';m=None;original=None;source=None;snap0=None;net=None;attempts=None
    try:
        m=load_qalib()
        net=m.forbid_network()
        attempts=net.__enter__()
        m.insist(sys.version_info[:3]==(3,13,16),'PYTHON_NOT_PINNED')
        phase='PINNED_ORIGINAL_FILES'
        home=Path.home()/'Downloads';roots=[home,Path.cwd(),Path(__file__).resolve().parent]
        wp=m.pinned_file(None,roots,['TASK0003_V05_CANONICAL_OFFLINE_FINAL_v3*.py'],m.WRAPPER_SHA,'WRAPPER_MISSING')
        d=m.static_wrapper(wp)
        ap=m.pinned_file(None,roots,['QA04_V05_FINAL_AB_v3*.json'],m.A_REPORT_SHA,'EXACT_A_REPORT_MISSING')
        prior=json.loads(ap.read_bytes())
        m.insist(prior['check_A']=='PASS' and prior.get('source_mutated') is False and
                 prior['checks'].get('full_raw_parquet_sqlite_lineage')=='PASS' and
                 prior['checks'].get('source_doi_8_and_147_issues')=='PASS',
                 'PRIOR_CHECK_A_NOT_PASS')
        result['check_A']='PASS'
        result['checks']['prior_A_v3_exact_report_sha']='PASS'
        phase='PATH_SAFETY'
        original=d['work'].resolve(strict=True)
        source=d['source'].resolve(strict=True)
        checkout=d['checkout'].resolve(strict=True)
        qa=args.qa_root.expanduser().resolve(strict=True)
        rpt=args.report.expanduser().resolve(strict=False)
        m.insist(not rpt.exists() and rpt.parent.is_dir(),'REPORT_PATH_NOT_FRESH')
        m.insist(qa.is_dir() and not qa.is_symlink() and
                 not qa.is_relative_to(original) and not qa.is_relative_to(source) and
                 not qa.is_relative_to(checkout) and
                 not original.is_relative_to(qa) and not source.is_relative_to(qa) and
                 not checkout.is_relative_to(qa) and
                 not rpt.is_relative_to(qa) and not rpt.is_relative_to(original),
                 'QA_ISOLATION_VIOLATION')
        m.safe_tree(qa)
        phase='ORIGINAL_IMMUTABILITY_BASELINE'
        snap0=m.exact_snapshot(original)
        adapter_sha=m.sha(d['adapted'])
        manifest=m.manifest_read(snap0,adapter_sha)
        orig_corpus_inv=m.inventory_snapshot(snap0,manifest)
        orig_input_inv=m.input_inventory(original)
        orig_source_inv=m.file_inventory(source)
        m.insist(m.fingerprint(orig_corpus_inv)==prior['digests']['original_corpus_inventory'] and
                 m.fingerprint(orig_input_inv)==prior['digests']['original_input_inventory'] and
                 m.fingerprint(orig_source_inv)==prior['digests']['original_source_inventory'],
                 'ORIGINAL_CHANGED_SINCE_CHECK_A')
        result['checks']['original_exact_A_v3_inventories']='PASS'
        phase='PINNED_ENVIRONMENT'
        m.insist(d['deps'].is_dir(),'PINNED_DEPS_NOT_FOUND')
        import subprocess
        head=subprocess.check_output(['git','-C',str(checkout),'rev-parse','HEAD'],text=True).strip()
        m.insist(head=='ae2dd8131fb7840ccb6f0ac9332dcf31ee4776ea','PINNED_CHECKOUT_DRIFT')
        sys.path.insert(0,str(d['deps']))
        import pyarrow as pa
        import pyarrow.parquet as pq
        import numpy as np
        m.insist(pa.__version__=='26.0.0' and np.__version__=='2.3.5','DEPENDENCY_DRIFT')
        uid,us=m.source_uid(source,d)
        phase='EXACT_REBUILD_BYTE_ATTESTATION'
        inp=qa/'input'
        m.insist(inp.is_dir() and inp.parent==qa,'B_INPUT_MISSING')
        m.insist(m.input_inventory(inp)==orig_input_inv,'B_INPUT_DIFF')
        before=inp/'corpus-v3'/m.MANIFEST_SHA
        after=qa/'restore_v7'/'corpus-v3'/m.MANIFEST_SHA
        m.insist(before.is_dir()!=after.is_dir(), 'B_REBUILD_ROOT_AMBIGUOUS')
        where=before if before.is_dir() else after
        bm=m.manifest_read(where,adapter_sha)
        rebuilt_inv=m.inventory_snapshot(where,bm)
        m.insist(rebuilt_inv==orig_corpus_inv,'B_REBUILT_753_SHA_MISMATCH')
        result['checks']['exact_builder_rebuild_753_file_hash_identity']='PASS'
        print('QA04_B_V7_REBUILD_REATTEST_PASS files=753',flush=True)
        # No extra copy. Verify metadata and all rows after changing restore root.
        phase='ATOMIC_REHOME_NO_COPY'
        moved=rehome_snapshot(before,after,m)
        result['rehome_state']=moved
        phase='RELOCATED_SNAPSHOT_READBACK'
        rm=m.manifest_read(after,adapter_sha)
        relocated_inv=m.inventory_snapshot(after,rm)
        m.insist(relocated_inv==orig_corpus_inv,'RELOCATED_753_SHA_MISMATCH')
        # All frozen scientific inputs remain in original authenticated source
        # and in the isolated raw clone, not in a new large disk copy.
        raw=m.parse_raw(inp,uid)
        counts=m.parquet_read(after,inp,raw,rm,uid,pq)
        result['checks']['relocated_750_parquet_and_sqlite_complete_row_readback']='PASS'
        result['counts']=counts
        phase='SQLITE_MEMORY_RESTORE'
        mr=sqlite_memory_restore(after/'working.sqlite',set(uid))
        result['checks']['sqlite_independent_memory_backup_restore']='PASS'
        result['memory_restore_counts']=mr
        phase='FINAL_IMMUTABILITY'
        m.insist(m.input_inventory(original)==orig_input_inv and
                 m.file_inventory(source)==orig_source_inv and
                 m.inventory_snapshot(snap0,manifest)==orig_corpus_inv,
                 'ORIGINAL_MUTATION')
        m.insist(m.input_inventory(inp)==orig_input_inv and
                 m.inventory_snapshot(after,rm)==orig_corpus_inv,
                 'ISOLATED_MUTATION')
        result['checks']['original_and_qa_inputs_unchanged']='PASS'
        result['digests']={'original':m.fingerprint(orig_corpus_inv),'relocated':m.fingerprint(relocated_inv)}
        result['check_B']='PASS_REBUILD_RELOCATE_MEMORY_DB_RESTORE'
        result['overall_independent_V05_canonical_QA']='PASS_TECHNICAL_WITH_RESTORE_SCOPE_LIMIT'
        result['blocking_reason']=None
        result['materialization_limit']='ELIGIBILITY_EXCLUSION_DERIVED_NOT_PERSISTED'
        result['source_mutated']=False
        m.insist(attempts[0]==0,'NETWORK_ATTEMPT')
        print('QA04_CHECK_B_RESTORE_READBACK_PASS snapshot_rehomed_no_copy=true sqlite_memory_backup=true',flush=True)
    except Exception as e:
        reason=str(e) if m is not None and isinstance(e,m.QAStop) else 'UNEXPECTED_'+type(e).__name__.upper()
        result['blocking_reason']=reason if re.fullmatch('[A-Z][A-Z0-9_]+',reason) else 'UNEXPECTED_ERROR'
        result['error_phase']=phase
        result['error_class']=type(e).__name__.upper()
        if isinstance(e,OSError):
            result['error_errno']=e.errno
            result['error_winerror']=getattr(e,'winerror',None)
        result['checks']['stop']='OPEN'
    finally:
        if attempts is not None:result['network_calls']=attempts[0]
        if net is not None:net.__exit__(None,None,None)
        if m is not None and original is not None and source is not None and snap0 is not None:
            try:
                unchanged=(m.fingerprint(m.input_inventory(original))==prior['digests']['original_input_inventory'] and
                           m.fingerprint(m.file_inventory(source))==prior['digests']['original_source_inventory'] and
                           m.fingerprint(m.file_inventory(snap0))==prior['digests']['original_corpus_inventory'])
                result['source_mutated']=not unchanged
                if not unchanged:
                    result['overall_independent_V05_canonical_QA']='BLOCKED'
                    result['blocking_reason']='ORIGINAL_DATA_CHANGED'
            except Exception:
                result['checks']['final_immutability']='OPEN'
        try:
            rpt=args.report.expanduser();rpt.parent.mkdir(parents=True,exist_ok=True)
            with rpt.open('x',encoding='utf8',newline='\n') as f:
                json.dump(result,f,ensure_ascii=False,indent=2,sort_keys=True);f.write('\n')
        except OSError:
            print('QA04_V7_REPORT_NOT_WRITTEN',flush=True)
        print('QA04_V05_FINAL '+result['overall_independent_V05_canonical_QA']+
              ' A='+result['check_A']+' B='+result['check_B']+
              ' reason='+str(result['blocking_reason'])+
              ' phase='+result.get('error_phase','COMPLETED')+
              ' network_calls='+str(result['network_calls']),flush=True)
    return 0 if result['overall_independent_V05_canonical_QA'].startswith('PASS') else 2

if __name__=='__main__':
    raise SystemExit(main())
