import os
import io
import ast
import sys
import logging
import textwrap
import traceback
import collections
from opster import command, dispatch, Dispatcher

class Visitor(ast.NodeTransformer):
    """ special ast visitor, parses code chunks from string into single code
    objects do not set maxdepth bigger than 1, except you know what you do, but
    probaly the compilation will fail"""

    def __init__(self,inputfilename,logger,maxdepth=1):
        self.maxdepth = maxdepth
        self.inputfilename = inputfilename
        self.logger = logger
        self.CodeChunk = collections.namedtuple('CodeChunk',['codeobject','source','assign'])
        self.interactive = False

    def _get_last_lineno(self,node):
        maxlineno = 0
        for x in ast.walk(node):
            if hasattr(x,'lineno') and x.lineno > maxlineno:
                maxlineno = x.lineno
        return maxlineno

    def _autoprint(self ,node):
        # implement autoprinting discovery
        if type(node) == ast.Assign:
            # test if simple assignement or trough some expression
            bmc = []
            for x in ast.iter_child_nodes(node):
                if not type(x) in (ast.Name,ast.Num,ast.Str):
                    bmc.append(x)
            if len(bmc)>0:
                if hasattr(node.targets[0],'id'):
                    return node.targets[0].id

    def _compile(self,node,auto=None):
        try:
            codeobject = compile(ast.Module([node]),self.inputfilename,'exec')
        except:
            self.logger.exception(
                'failed to compile "{0}", {1}'.format(
                    node,traceback.format_exc()))
        #auto = self._autoprint(node)
        return self.CodeChunk(codeobject,node.source,auto)

    def _import_matplotlib(self,modpart):
        if not 'matplotlib.pyplot' in sys.modules:
            self.logger.info('detected "{0}" and imported matplotlib'
            ' before to choose backend "Agg"'.format(modpart))
            return self.CodeChunk(
                    compile('import matplotlib;matplotlib.use("Agg")',
                        '<rstscript.dynamic>','exec'),'','')
        else:
            self.logger.info('detected import of matplotlib.pyplot, '
            'but backend was already choosen')

    def _detect_matplotlib(self,names,module=None):
        if module:
            for modpart in module.split('.'):
                if modpart in ['pyplot','pylab','sympy']:
                    return self._import_matplotlib(modpart)
        for name in names:
            if name.name in ['pyplot','pylab','sympy']:
                return self._import_matplotlib(name.name)

    def visit_Import(self,node):
        newnode = self._detect_matplotlib(node.names)
        if newnode:
            yield newnode
        yield self._compile(node)

    def visit_ImportFrom(self,node):
        newnode = self._detect_matplotlib(node.names,module=node.module)
        if newnode:
            yield newnode
        yield self._compile(node)


    def visit_Expr(self,node):
        if type(node.value) == ast.Name:
            yield self._compile(node,auto=node.value.id)
        else:
            yield self._compile(node)


    def visit(self, node, start_lineno,raw,depth=0):
        """Visit a node."""
        if depth >= self.maxdepth:
            method = 'visit_' + node.__class__.__name__
            visitor = getattr(self, method, None)
            # get source code of the node, must be before the next statement
            startline = node.lineno-1
            endline = self._get_last_lineno(node)
            node.source = '\n'.join(raw[startline:endline])
            #print('last line',self._get_last_lineno(node),'source',node.source)
            node.lineno = node.lineno + start_lineno
            if visitor:
                yield from visitor(node)
            else:
                yield self._compile(node)
        else:
            depth += 1
            for child in ast.iter_child_nodes(node):
                yield from self.visit(child,start_lineno,raw,depth=depth)


class Litter(object):
    def __init__(self,figdir='',stop_on_error=True,ipython_style=False,loglevel='WARNING',inputfilename='',inputfile=None,outputfilename='',outputfile=None,**kwargs):
        self.plt = None
        if figdir:
            self._figdir = figdir
        else:
            self._figdir = None
        if inputfilename:
            self.inputfile = open(inputfilename,'r')
        elif inputfile:
            self.inputfile = inputfile
        self.inputfilename = self.inputfile.name
        sys.path.append(os.path.abspath('.'))
        if outputfilename:
            self.outputfile = open(outputfilename,'wb')
        elif outputfile:
            self.outputfile = outputfile
        self._raw = None
        self.logger = logging.getLogger('litter')
        self.logger.setLevel(loglevel)
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter('%(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        handler.setLevel(loglevel)
        self.logger.addHandler(handler)
        self.visitor = Visitor(self.inputfile.name,self.logger)
        self.globallocal = {}
        self.autoprinting = True
        self.ipythonstyle = ipython_style
        self.stderr = io.StringIO()
        self.stdout = io.StringIO()
        self.traceback = io.StringIO()
        self.stdout_sys = sys.stdout
        self.stderr_sys = sys.stderr
        self.ResultChunk = collections.namedtuple(
            'ResultChunk',['codechunk','stderr','stdout','traceback'])
        self.results = {}
        self.stop_on_error = stop_on_error
        self.reference = {}

    def visit(self,tree,linenumber,source):
        return self.visitor.visit(tree,linenumber,source.splitlines())

    def chunks(self):
        chunk = io.StringIO()
        code = False
        linenumber = 1
        for i,line in enumerate(self.inputfile):
            if not line.strip() or line.startswith('#'):
                if code:
                    yield (linenumber,code,chunk.getvalue())
                    chunk.seek(0)
                    chunk.truncate()
                    code = not code
                    linenumber = i+1
                if line.startswith('#'):
                    chunk.write(line[1:])
                else:
                    chunk.write(line)
            else:
                if not code:
                    yield (linenumber,code,chunk.getvalue())
                    chunk.seek(0)
                    chunk.truncate()
                    code = not code
                    linenumber = i+1
                chunk.write(line)
        yield (linenumber,code,chunk.getvalue())


    @property
    def figdir(self):
        if not self._figdir:
            self._figdir=os.path.abspath(os.path.dirname(self.outputfile.name))
        return self._figdir

    def _saveallfigures(self,result):
        if not self.plt:
            if 'matplotlib.pyplot' in sys.modules:
                from matplotlib import pyplot
                self.plt = pyplot
                self.logger.info('imported matplotlib.pyplot')
            else:
                raise StopIteration
        for num in self.plt.get_fignums():
            if num > 1:
                self.logger.error('there are several figures in this chunks, not supported so far')
            else:
                label,desc = self._get_label(result)
                if label:
                    fig = self.plt.figure(num)
                    name = '{0}.png'.format(label)
                    figpath =os.path.join(self.figdir,name)
                    fig.savefig(figpath)
                    ref = '\n![{desc}\label{{{label}}}]({path})\n'.format(label=label,desc=desc,path=figpath)
                    self.logger.info('saved figure "{0}" to "{1}"'.format(label,figpath))
                    self.reference[label] = figpath
                    yield (False,ref)

    def _get_label(self,result):
        if '#:' in result.codechunk.source:
            s = result.codechunk.source
            t = s[s.find('#:')+2:]
            if ':' in t:
                return t.split(':')
            else:
                return t,t
        else:
            return None,None

    def process(self):
        for (linenumber,code,source) in self.chunks():
            if code:
                tree = ast.parse(source)
                for chunk in self.visit(tree,linenumber-1,source):
                    result = self.execute(chunk)
                    yield (code,result)
                    yield from self._saveallfigures(result)
                    if result.traceback and self.stop_on_error:
                        raise StopIteration
            else:
                yield (code,source.format(self.globallocal))

    def inter(self):
        from IPython.terminal.embed import InteractiveShellEmbed
        from IPython.terminal.interactiveshell import TerminalMagics

        inter = InteractiveShellEmbed()
        magics = TerminalMagics(inter)
        t = threading.Thread(target=inter)
        t.start()
        import time
        time.sleep(2)
        magics.store_or_execute('a=2\nprint(a)',None)

    def format(self):
        wascode = False
        tmp = io.StringIO()
        for (code,result) in self.process():
            if not code:
                if wascode and tmp.tell():
                    val = tmp.getvalue()
                    self.outputfile.write(b'\n~~~python\n')
                    self.outputfile.write(val.encode('utf-8'))
                    self.outputfile.write(b'~~~\n\n')
                    tmp.seek(0)
                    tmp.truncate()
                    wascode = False
                if not '#>' in result:
                    self.outputfile.write(result.encode('utf-8'))
            else:
                wascode = True
                self.format_result(tmp,result)
        for (label,ref) in self.reference.items():
            self.outputfile.write('\n[{0}]: {1}\n'.format(label,ref).encode('utf-8'))

    def format_result(self,out,res):
        if not '#>' in res.codechunk.source and res.codechunk.source:
            if self.ipythonstyle:
                out.write('In [{0}]: '.format(res.codechunk.codeobject.co_firstlineno))
                out.write(res.codechunk.source)
                out.write('\n')
            elif not res.codechunk.assign:
                out.write(res.codechunk.source)
                out.write('\n')
        if res.stdout:
            if self.ipythonstyle:
                out.write('Out[{0}]: '.format(res.codechunk.codeobject.co_firstlineno))
            out.write(res.stdout)
            out.write('\n')
        if res.stderr:
            out.write(res.stderr)
            out.write('\n')
        if res.traceback:
            out.write(res.traceback)
            out.write('\n')
        elif self.autoprinting and res.codechunk.assign:
            coa = res.codechunk.assign
            result = self.globallocal[coa]
            if self.ipythonstyle:
                out.write('Out[{0}]: '.format(res.codechunk.codeobject.co_firstlineno))
                out.write(str(result))
            else:
                out.write('{0} = {1}'.format(coa,result))
            out.write('\n')


    def execute(self,codechunk):
        sys.stdout = self.stdout
        sys.stderr = self.stderr
        self.stdout.seek(0)
        self.stderr.seek(0)
        self.traceback.seek(0)
        tr = ''
        try:
            exec(codechunk.codeobject,self.globallocal,self.globallocal)
        except:
            tr = traceback.format_exc().strip()
            # remove all line until a line containing rstscript.dynamic except
            # the first
            st = tr.find('\n')+1
            en = tr.find('File "{0}"'.format(self.inputfilename))
            self.traceback.write(tr[:st])
            self.traceback.write(tr[en:])
        finally:
            sys.stdout = self.stdout_sys
            sys.stderr = self.stderr_sys
        if tr:
            self.logger.warn(
                'failed on line {0} with {1}'.format(
                    codechunk.codeobject.co_firstlineno,tr[tr.rfind('\n')+1:]))
        self.stdout.truncate()
        self.stderr.truncate()
        rc = self.ResultChunk(
            codechunk,self.stderr.getvalue(),
            self.stdout.getvalue(),self.traceback.getvalue()
        )
        self.stderr.seek(0)
        self.stderr.truncate()
        self.traceback.seek(0)
        self.traceback.truncate()
        self.stdout.seek(0)
        self.stdout.truncate()
        return rc

process = Dispatcher(globaloptions=[
    ('s','stop-on-error',False,'stop if an error occurs'),
    ('l','loglevel','WARNING','set the log level'),
    ('i','ipython-style',False,'ipython in out style'),
    ('h','highlighting-style','pygments','highlighting style'),
    ('v','version','0.0.1','version of the file'),
])

d = Dispatcher()
d.nest('process',process,'process the python input')

@process.command(name='md',usage='inputfile -o outpufile')
def process_md(inputfilename,outputfilename='',**kwargs):
    if not outputfilename:
        with io.BytesIO() as tmp:
            li = Litter(outputfile=tmp,inputfilename=inputfilename,figdir=os.path.abspath('.'),**kwargs)
            li.format()
            tmp.seek(0)
            sys.stdout.write(tmp.read().decode('utf-8'))
    else:
        li = Litter(outputfilename=outputfilename,inputfilename=inputfilename,**kwargs)
        li.format()


@process.command(name='pdf',usage='inputfile -o outpufile')
def process_pdf(inputfilename,outputfilename,**kwargs):
    from sh import pandoc
    import tempfile
    with tempfile.NamedTemporaryFile() as tmp:
        li = Litter(outputfile=tmp.file,inputfilename=inputfilename,figdir=os.path.abspath(os.path.dirname(outputfilename)),**kwargs)
        li.format()
        tmp.file.flush()
        kwargs.get('version')
        pandoc(tmp.name,'-o',outputfilename,
            '--template',os.path.join(
                os.path.dirname(__file__),'data','template.tex'),'-V','version=%s'%kwargs.get('version'),'--highlight-style',kwargs.get('highlighting_style'))


@d.command(usage='input output')
def mdto(inputfilename,outputfilename,highlight='pygments'):
    """ convert markdown to pdf using pandoc"""
    from sh import pandoc
    pandoc(inputfilename,'-o',outputfilename,'--highlight-style',highlight,
        '--template',os.path.join(
            os.path.dirname(__file__),'data','template.tex'),'-V','version=0.0.1')


def main():
    d.dispatch()

if __name__ == '__main__':
    main()


