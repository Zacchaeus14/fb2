#!/bin/bash
#SBATCH --job-name=pretrain1-exp4
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16GB
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
python -u pretrain1.py --ckpt /gpfsnyu/scratch/yw3642/hf-models/microsoft_deberta-v3-large \
--epochs 30 --batch_size 4 --lr 1e-5 --weight_decay 0 --seed -1 --max_len 1024 \
--exp 4 --mlm_prob 0.5 --gradient_checkpointing --resize_embedding
echo "FINISH"
