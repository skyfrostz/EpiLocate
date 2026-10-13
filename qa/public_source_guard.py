"""Public-source QA IO guard; generated fixtures only, never execution authority."""
import pathlib,sys

def pytest_sessionstart(session):
 def guard(event,args):
  if event=='open' and args and isinstance(args[0],(str,bytes)):
   value=str(args[0]);p=pathlib.Path(value)
   if '/EpiLocate-private/' in value or '/.local/private-bindings/' in value or ('/pytest-' not in value and ('/.local/phase2/' in value or '/hospital-release/' in value)):
    raise RuntimeError('PRIVATE_EVIDENCE_IO_FORBIDDEN_DURING_PUBLIC_QA')
   if p.suffix.lower() in {'.npy','.npz','.pth','.pt','.ckpt','.safetensors','.dcm','.dicom'}:
    if '/pytest-' not in value and '/pytest_of_' not in value and 'r85-readiness-synthetic-' not in value and 'epi-next-encoder-synthetic-' not in value:
     raise RuntimeError('NON_GENERATED_ASSET_IO_FORBIDDEN_DURING_PUBLIC_QA')
  if event=='socket.connect':
   address=args[1]
   if isinstance(address,tuple) and str(address[0]) not in ('127.0.0.1','localhost','::1'):
    raise RuntimeError('EXTERNAL_NETWORK_FORBIDDEN_DURING_PUBLIC_QA')
 sys.addaudithook(guard)
