#!/bin/bash
##train10-exp1 + linear hs
#SBATCH --job-name=train13-exp0-fold3
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=24GB
#SBATCH --time=167:00:00
#SBATCH --mail-type=END
#SBATCH --mail-user=yw3642@nyu.edu
#SBATCH --output=log/%x-%A.out
#SBATCH --error=log/%x-%A.err
#SBATCH --gres=gpu:1
#SBATCH -p aquila
#SBATCH --nodelist=agpu8

module purge
module load anaconda3 cuda/11.1.1

nvidia-smi
nvcc --version
cd /gpfsnyu/scratch/yw3642/fb2/src

echo "START"
source deactivate
source /gpfsnyu/packages/anaconda3/5.2.0/bin/activate kaggle
python -u train13.py --ckpt /gpfsnyu/scratch/yw3642/hf-models/microsoft_deberta-v3-large \
--epochs 12 --batch_size 2 --lr 5e-6 --lr_head 1e-4 --seed -1 --fold 3 --exp 0 \
--use_pretrained /gpfsnyu/scratch/yw3642/fb2/ckpt/pretrain0/exp6/pretrained_model.pt \
--adv_lr 1 --adv_eps 0.0002 --adv_after_epoch 1 --patience 30 --gradient_checkpointing --warmup_ratio 0.1 \
--hs_pooler_dropout 0.5 --lr_hs_pooler 1e-3
echo "FINISH"