"""Export spatial/fusion network; NumPy FFT retains original preprocessing.
Synthetic corpus verifies numerical behavior, never detector accuracy.
"""
import hashlib
import argparse
import json
import sys
from pathlib import Path
import numpy as np
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
import torch
import onnxruntime as ort
from model import DeepfakeService, extract_frequency_features

def numpy_frequency(images):
    gray=images.mean(axis=1,dtype=np.float32)
    height,width=gray.shape[-2:]
    window=np.hanning(height).astype(np.float32)[:,None]*np.hanning(width).astype(np.float32)[None,:]
    magnitude=np.log1p(np.abs(np.fft.fftshift(np.fft.fft2(gray*window),axes=(-2,-1)))).astype(np.float32)
    yy,xx=np.meshgrid(np.arange(height,dtype=np.float32),np.arange(width,dtype=np.float32),indexing='ij')
    radius=np.sqrt((yy-(height-1)/2)**2+(xx-(width-1)/2)**2)
    edges=np.linspace(0,max(radius.max(),1),9,dtype=np.float32)
    bands=[]
    for index in range(8):
        mask=(radius>=edges[index])&(radius<edges[index+1])
        bands.append((magnitude*mask).sum(axis=(-2,-1))/max(mask.sum(),1))
    # 224x224 divides exactly into original adaptive-average-pool 4x4 bins.
    pooled=gray.reshape(len(gray),4,height//4,4,width//4).mean(axis=(2,4)).reshape(len(gray),16)
    return np.concatenate([np.stack(bands,axis=1),pooled],axis=1).astype(np.float32)

class ExportNetwork(torch.nn.Module):
    def __init__(self, model): super().__init__();self.model=model
    def forward(self, images, frequency):
        spatial=self.model.pool(self.model.encoder(images)).flatten(1)
        return self.model.classifier(torch.cat([spatial,self.model.frequency_mlp(frequency)],dim=1))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--unfused',action='store_true',help='Disable exporter constant folding and ORT graph optimizations')
    args=parser.parse_args()
    suffix='-unfused' if args.unfused else ''
    out=root.parent/'artifacts';out.mkdir(exist_ok=True)
    service=DeepfakeService(root/'best_model.pt')
    wrapper=ExportNetwork(service.model).eval()
    report={'adopted':False,'torch_version':torch.__version__,'onnxruntime_version':ort.__version__,'unfused':args.unfused,'corpus':'50 synthetic normalized 224x224 RGB frame inputs, seed 7300930; numerical verification only','labels':{'0':'fake','1':'real'}}
    try:
        example=torch.zeros(1,3,224,224)
        torch.onnx.export(wrapper,(example,extract_frequency_features(example)),str(out/f'detector{suffix}.onnx'),input_names=['images','frequency'],output_names=['logits'],opset_version=17,dynamo=False,do_constant_folding=not args.unfused)
        options=ort.SessionOptions();options.intra_op_num_threads=1;options.inter_op_num_threads=1
        if args.unfused: options.graph_optimization_level=ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        runtime=ort.InferenceSession(str(out/f'detector{suffix}.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
        rng=np.random.default_rng(7300930);differences=[];labels=[];freqdiff=[];hashes=[]
        with torch.inference_mode():
            for index in range(50):
                pixels=rng.integers(0,256,(1,3,224,224),dtype=np.uint8)
                if index<10:pixels[:]=index*25
                images=(pixels.astype(np.float32)/255-np.array([.485,.456,.406],dtype=np.float32)[None,:,None,None])/np.array([.229,.224,.225],dtype=np.float32)[None,:,None,None]
                hashes.append(hashlib.sha256(images.tobytes()).hexdigest())
                frequency=numpy_frequency(images)
                original=torch.softmax(service.model(torch.from_numpy(images)),dim=1).numpy()[0]
                logits=runtime.run(None,{'images':images,'frequency':frequency})[0][0]
                shifted=logits-logits.max();actual=np.exp(shifted)/np.exp(shifted).sum()
                differences.append(float(np.abs(original-actual).max()))
                labels.append(bool(original.argmax()==actual.argmax()))
                freqdiff.append(float(np.abs(extract_frequency_features(torch.from_numpy(images)).numpy()-frequency).max()))
        report.update({'passed':all(labels) and max(differences)<=.001,'unchanged_labels':sum(labels),'maximum_absolute_probability_difference':max(differences),'raw_max_probability_differences':differences,'maximum_frequency_feature_difference':max(freqdiff),'corpus_sha256':hashes,'onnx_bytes':(out/f'detector{suffix}.onnx').stat().st_size,'promotion_gate':'Frame-level numerical checks alone do not prove video-level parity or memory improvement; PyTorch remains serving runtime.'})
    except Exception as exc: report.update({'passed':False,'error_type':type(exc).__name__,'error':str(exc)[:2000]})
    (out/f'onnx{suffix}-verification.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if not isinstance(v,list)}))

if __name__=='__main__':main()
