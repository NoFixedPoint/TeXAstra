"""Source-span experiment for an explicit subset of ordinary LaTeX.

This is NOT a general TeX parser. It never claims recovered engine provenance:
it adds attributes to known output-producing tokens and leaves unsupported
commands unmapped. A modified engine is required for arbitrary TeX semantics.
"""
import bisect
import re

RESET = r'\attribute\bakoattr=0 '
SYMBOLS = set('alpha beta gamma delta epsilon theta lambda mu pi sigma phi omega Gamma Delta Theta Lambda Pi Sigma Phi Omega sum prod int infty partial nabla times cdot pm mp leq geq neq in notin subset supset approx to rightarrow leftarrow ldots cdots sin cos tan log ln exp lim'.split())
TEXT_ARGS=set('section subsection subsubsection paragraph textbf textit emph textrm textsf texttt text operatorname'.split())
MATH_ARGS=set('mathrm mathbf mathit mathsf mathtt mathcal mathbb overline underline hat bar vec tilde'.split())
RAW_ARGS={'label':1,'input':1,'include':1,'begin':1,'end':1,'hspace':1,'vspace':1,'setcounter':2,'addtocounter':2,'rule':2}
FALLBACK_ARGS={'ref':1,'pageref':1,'eqref':1,'cite':1,'fixed':0,'globalword':0}
STRUCTURAL=set('par newpage clearpage noindent quad qquad smallskip medskip bigskip displaystyle textstyle scriptstyle scriptscriptstyle'.split())

class Instrumenter:
    def __init__(self):
        self.spans={}
        self.warnings=[]
        self.next_id=1
        self.file_slots={}
        self.file_ids={}

    def instrument(self,text,file):
        if file not in self.file_slots: self.file_slots[file]=len(self.file_slots)+1
        self.next_id=self.file_slots[file]*1000000
        for identifier in self.file_ids.get(file,[]):self.spans.pop(identifier,None)
        self.file_ids[file]=[]
        self.text=text; self.file=file; self.i=0
        self.lines=[0]+[m.end() for m in re.finditer('\n',text)]
        return self._sequence(False)

    def _mark(self,start,end,kind='token'):
        identifier=self.next_id; self.next_id+=1
        self.file_ids[self.file].append(identifier)
        line=bisect.bisect_right(self.lines,start)-1
        column=len(self.text[self.lines[line]:start].encode('utf-16-le'))//2
        endline=bisect.bisect_right(self.lines,end)-1
        endcolumn=len(self.text[self.lines[endline]:end].encode('utf-16-le'))//2
        self.spans[identifier]=dict(file=self.file,start=start,end=end,line=line,column=column,
                                   endLine=endline,endColumn=endcolumn,text=self.text[start:end],kind=kind)
        return rf'\attribute\bakoattr={identifier} '

    def _raw_group(self,opener='{',closer='}'):
        start=self.i
        if self.i>=len(self.text) or self.text[self.i]!=opener: return ''
        depth=0
        while self.i<len(self.text):
            c=self.text[self.i]; self.i+=1
            if c=='\\':
                if self.i<len(self.text): self.i+=1
            elif c==opener: depth+=1
            elif c==closer:
                depth-=1
                if depth==0: return self.text[start:self.i]
        return self.text[start:self.i]

    def _space(self):
        start=self.i
        while self.i<len(self.text) and self.text[self.i].isspace(): self.i+=1
        return self.text[start:self.i]

    def _argument(self,math):
        space=self._space()
        if self.i<len(self.text) and self.text[self.i]=='{':
            self.i+=1
            return space+'{'+self._sequence(math,stop='}')+'}'
        # A single unbraced math argument must remain one TeX field.
        start=self.i
        if self.i<len(self.text):
            if self.text[self.i]=='\\':
                m=re.match(r'\\[A-Za-z@]+|\\.',self.text[self.i:]); self.i+=len(m[0])
            else: self.i+=1
        return space+'{'+self._mark(start,self.i)+self.text[start:self.i]+'}'

    def _command(self,math):
        start=self.i
        m=re.match(r'\\([A-Za-z@]+|.)',self.text[self.i:])
        if not m: self.i+=1; return '\\'
        name=m[1]; self.i+=len(m[0]); command=m[0]
        if name in SYMBOLS:
            return self._mark(start,self.i)+command+' '+RESET
        if name in ('frac','dfrac','tfrac','binom'):
            return RESET+command+self._argument(True)+self._argument(True)+RESET
        if name=='sqrt':
            optional=''
            if self.i<len(self.text) and self.text[self.i]=='[':
                optional=self._raw_group('[',']')
            return RESET+command+optional+self._argument(True)+RESET
        if name in TEXT_ARGS or name in MATH_ARGS:
            if self.i<len(self.text) and self.text[self.i]=='*': command+='*'; self.i+=1
            return RESET+command+self._argument(name in MATH_ARGS)+RESET
        if name in ('left','right','big','Big','bigl','bigr','Bigl','Bigr'):
            # Keep delimiter scanner intact; map the complete delimiter command.
            self._space()
            if self.i<len(self.text) and self.text[self.i]=='\\':
                delim=re.match(r'\\[A-Za-z]+|\\.',self.text[self.i:]); self.i+=len(delim[0])
            elif self.i<len(self.text): self.i+=1
            return self._mark(start,self.i)+self.text[start:self.i]+' '+RESET
        if name=='pair':
            arg=self._argument(math)
            origin=self._mark(start,self.i,'macro-origin')
            # The macro's generated '+' belongs to its invocation, not to the
            # last argument glyph. Restore that origin at each argument exit.
            arg=arg[:-1]+origin+'}'
            return origin+command+arg+RESET
        if name in FALLBACK_ARGS:
            for _ in range(FALLBACK_ARGS[name]): self._space(); self._raw_group()
            return self._mark(start,self.i,'macro-origin')+self.text[start:self.i]+RESET
        if name in RAW_ARGS:
            for _ in range(RAW_ARGS[name]): self._space(); self._raw_group()
            raw=self.text[start:self.i]
            if name=='begin' and raw.endswith('{tikzpicture}'):
                if self.i<len(self.text) and self.text[self.i]=='[': raw+=self._raw_group('[',']')
            return RESET+raw
        if name in STRUCTURAL or len(name)==1:
            return RESET+command+(' ' if name in STRUCTURAL else '')
        self.warnings.append(dict(file=self.file,offset=start,command=name,reason='unknown command: arguments are not instrumented'))
        # Preserve adjacent optional/mandatory arguments byte-for-byte. Attributes
        # are cleared so unsupported expansion is never assigned a nearby token.
        end=self.i
        while True:
            self._space()
            if self.i<len(self.text) and self.text[self.i] in '{[':
                ch=self.text[self.i]; self._raw_group(ch,'}' if ch=='{' else ']'); end=self.i
            else: self.i=end; break
        return RESET+self.text[start:self.i]+' '+RESET

    def _sequence(self,math,stop=None):
        out=[]
        while self.i<len(self.text):
            c=self.text[self.i]
            if c==stop: self.i+=1; break
            if self.text.startswith(r'\begin{tikzpicture}',self.i):
                out.append(self._tikz()); continue
            if self.text.startswith(r'\begin{align',self.i): math=True
            if self.text.startswith(r'\end{align',self.i): math=False
            if c=='%':
                end=self.text.find('\n',self.i)
                if end<0: end=len(self.text)
                out.append(self.text[self.i:end]); self.i=end; continue
            if c=='\\': out.append(self._command(math)); continue
            self.i+=1
            if c=='$': math=not math; out.append(RESET+'$'+RESET)
            elif c=='{': out.append('{'+self._sequence(math,stop='}')+'}')
            elif c in '_^' and math: out.append(c+self._argument(True))
            elif c.isspace() or c in '&}': out.append(c)
            elif c=='~': out.append(RESET+c)
            else: out.append(self._mark(self.i-1,self.i)+c)
        return ''.join(out)

    def _tikz(self):
        # Deliberately bounded: ordinary \node ... {label}; statements. Graphics
        # commands/options stay byte-identical; label bodies use the same mapper.
        start=self.i
        match=re.search(r'\\end\{tikzpicture\}',self.text[start:])
        end=len(self.text) if not match else start+match.end()
        out=[RESET]
        while self.i<end:
            node=re.search(r'\\node\b[^;{}]*\{',self.text[self.i:end])
            if not node: out.append(self.text[self.i:end]); self.i=end; break
            label=self.i+node.end()
            out.append(self.text[self.i:label]); self.i=label
            out.append(self._sequence(False,stop='}')+'}')
        return ''.join(out)+RESET
