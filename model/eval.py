import torch.nn.functional as F
import torch
import pandas as pd
from common.util import get_batch_of_device
from torch.utils.data import DataLoader
import numpy as np
def pairwise_match_question(question,answers,model,vocab,max_sentence_len,device,tokenizer=list,batch_size=32):
    from  common.datautil import  TextDataset
    n = len(answers)
    qds = TextDataset([question]*n,vocab,max_sentence_len,tokenizer)
    ans_ds = TextDataset(answers,vocab,max_sentence_len,tokenizer)
    q_dl = DataLoader(qds , batch_size=batch_size,shuffle=False)
    ans_dl = DataLoader(ans_ds , batch_size=batch_size,shuffle=False)
    sim_list = []
    for batch_q,batch_ans in zip(q_dl,ans_dl):
        batch_q =  get_batch_of_device(batch_q,device)
        batch_ans =  get_batch_of_device(batch_ans,device)
        qv = model.forward_question(batch_q)
        av = model.forward_answer(batch_ans )      
        qv = qv.detach()
        av = av.detach()
        sim = cosine_similarity(qv,av)
        sim_list.append(sim)
    sim_t = torch.cat(sim_list,0)
    print(sim_t)
    _,sort_idx = torch.sort(sim_t,descending=True)
    if sim_t.is_cuda:
        sim_t = sim_t.cpu().numpy()
        sort_idx = sort_idx.cpu().numpy()
    np_answers = np.array(answers)
    np_answers = np_answers[sort_idx].tolist()
    sim_t = sim_t[sort_idx].tolist()
    return list(zip(np_answers,sim_t))

def match_all(model,loader,device):
    qids = []
    ans_ids = []
    sim_list = []
    for batch in loader:
        batch =  get_batch_of_device(batch,device)
        qv = model.forward_question(batch['q'])
        av = model.forward_answer(batch['ans'])
        qv = qv.detach()
        av = av.detach()
        sim = cosine_similarity(qv,av)
        qids.append(batch['question_id'])
        ans_ids.append(batch['ans_id'])
        sim_list.append(sim)
    sim_t = torch.cat(sim_list,0)
    qid_t = torch.cat(qids,0)
    ans_t = torch.cat(ans_ids,0)

    if sim_t.is_cuda:
        d =  {'question_id':qid_t.cpu().numpy(),'ans_id':ans_t.cpu().numpy(),'sim':sim_t.cpu().numpy()}
    else:
        d = {'question_id':qid_t.numpy(),'ans_id':ans_t.numpy(),'sim':sim_t.numpy()}
    df = pd.DataFrame(data=d)
    df = df.groupby(["question_id"]).apply(lambda x: x.sort_values(["sim"], ascending = False)).reset_index(drop=True)
    return df

class Evaluator():
    def __init__(self,evaluate_file):
        self.eva_df =  pd.read_csv(evaluate_file)
    #macro accuracy
    def evaluate_accuracy(self,preds,k=1):
        def accuracy_at_k(g):
            gdf = g.head(k)
            qid = g['question_id'].values[0]
            edf = self.eva_df.loc[(self.eva_df['question_id']==qid) & (self.eva_df['label']==1)]
            _ = set(gdf['ans_id'].values)&set(edf['ans_id'].values)
            #print(set(gdf['ans_id'].values))
            #print(set(edf['ans_id'].values))
            #print(len(_)/n)
            return len(_)/k
        accu = preds.groupby(['question_id']).apply(accuracy_at_k).reset_index(name='accu')    
        m = accu['accu'].mean()
        return m


def cosine_similarity(q_vectors,a_vectors):
    return F.cosine_similarity(q_vectors,a_vectors,1)


def embedding_loss(pos_sims,neg_sims,M=0.2):
    diff = M-pos_sims+neg_sims
    _loss = torch.clamp(diff, min=0)
    return torch.mean(_loss)




#prediction: ranked answer id list , ground_truth : postive answer ids
def accuracy(prediction,ground_truth,k=1):
    pred_k = prediction[0:k]
    return len(set(pred_k)&set(ground_truth))/k