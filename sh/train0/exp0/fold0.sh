#!/bin/bash
#SBATCH --job-name=train0-exp0-fold0
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
#SBATCH --nodelist=agpu7

module purge
module load anaconda3 cuda/11.1.1

nvidia-smi
nvcc --version
cd /gpfsnyu/scratch/yw3642/fb2/src

echo "START"
source deactivate
source /gpfsnyu/packages/anaconda3/5.2.0/bin/activate kaggle
python -u train0.py --ckpt /gpfsnyu/scratch/yw3642/hf-models/microsoft_deberta-v3-large \
--epochs 5 --batch_size 2 --lr 1e-5 --weight_decay 0 --seed 42 --max_len 1024 \
--exp 0 --fold 0
echo "FINISH"