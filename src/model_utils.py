import torch
from torch.optim import AdamW, Adam, RAdam
from transformers import AutoModel, get_linear_schedule_with_warmup, AutoConfig
from transformers.modeling_outputs import TokenClassifierOutput
from transformers.models.deberta.modeling_deberta import StableDropout
from transformers.trainer_pt_utils import get_parameter_names
import bitsandbytes as bnb
import random


def get_deberta_v2_layers(model, n):
    for layer in model.deberta.encoder.layer[-n:]:
        yield layer


# Re-init script copied from https://github.com/asappresearch/revisit-bert-finetuning/blob/master/run_glue.py
def reinit_pooler(model):
    model.pooler.dense.weight.data.normal_(mean=0.0, std=model.config.initializer_range)
    model.pooler.dense.bias.data.zero_()
    for p in model.pooler.parameters():
        p.requires_grad = True


def reinit_layers(model, n=0):
    if model.config.model_type == "deberta-v2":
        layer_generator = get_deberta_v2_layers(model, n)
    else:
        raise NotImplementedError
    for layer in layer_generator:
        for module in layer.modules():
            if isinstance(module, (torch.nn.Linear, torch.nn.Embedding)):
                module.weight.data.normal_(mean=0.0, std=model.config.initializer_range)
            elif isinstance(module, torch.nn.LayerNorm):
                module.bias.data.zero_()
                module.weight.data.fill_(1.0)
            if isinstance(module, torch.nn.Linear) and module.bias is not None:
                module.bias.data.zero_()


# https://github.com/huggingface/transformers/blob/v4.20.1/src/transformers/trainer.py#L209
def get_optimizer_grouped_parameters(model, n=0):
    raise NotImplementedError


class Model3(torch.nn.Module):
    def __init__(self, ckpt, use_stable_dropout=False, normal_init=False):
        super().__init__()
        self.backbone = AutoModel.from_pretrained(ckpt)
        dropout_class = StableDropout if use_stable_dropout else torch.nn.Dropout
        self.dropout1 = dropout_class(0.1)
        self.dropout2 = dropout_class(0.2)
        self.dropout3 = dropout_class(0.3)
        self.dropout4 = dropout_class(0.4)
        self.dropout5 = dropout_class(0.5)
        self.classifier = torch.nn.Linear(self.backbone.config.hidden_size, 3)
        if normal_init:
            self.classifier.weight.data.normal_(mean=0.0, std=self.backbone.config.initializer_range)
            self.classifier.bias.data.zero_()

    def forward(self, input_ids=None, attention_mask=None, labels=None):
        outputs = self.backbone(input_ids=input_ids, attention_mask=attention_mask)
        sequence_output = outputs[0]
        logits1 = self.classifier(self.dropout1(sequence_output))
        logits2 = self.classifier(self.dropout2(sequence_output))
        logits3 = self.classifier(self.dropout3(sequence_output))
        logits4 = self.classifier(self.dropout4(sequence_output))
        logits5 = self.classifier(self.dropout5(sequence_output))
        logits = (logits1 + logits2 + logits3 + logits4 + logits5) / 5
        loss = None
        if labels is not None:
            loss_fct = torch.nn.CrossEntropyLoss()
            loss = loss_fct(logits.view(-1, 3), labels.view(-1))
        return TokenClassifierOutput(loss=loss, logits=logits)

def process_state_dict(state_dict, ckpt):
    state_dict = strip_state_dict(state_dict, ckpt)
    return {k: v for k, v in state_dict.items() if 'decoder' not in k}

def strip_state_dict(state_dict, ckpt):
    if 'deberta' in ckpt:
        prefix = 'deberta.'
    elif 'roberta' in ckpt:
        prefix = 'roberta.'
    elif 'funnel' in ckpt:
        prefix = 'funnel.'
    elif 'longformer' in ckpt:
        prefix = 'longformer.'
    else:
        raise NotImplementedError
    return {k[len(prefix):]: v for k, v in state_dict.items() if k.startswith(prefix)}


class Model5(torch.nn.Module):
    def __init__(self, ckpt, num_train_steps, learning_rate):
        super().__init__()
        self.backbone = AutoModel.from_pretrained(ckpt)
        self.dropout1 = StableDropout(0.1)
        self.dropout2 = StableDropout(0.2)
        self.dropout3 = StableDropout(0.3)
        self.dropout4 = StableDropout(0.4)
        self.dropout5 = StableDropout(0.5)
        self.classifier = torch.nn.Linear(self.backbone.config.hidden_size, 3)
        self.num_train_steps = num_train_steps
        self.learning_rate = learning_rate


    def forward(self, input_ids=None, attention_mask=None, labels=None):
        outputs = self.backbone(input_ids=input_ids, attention_mask=attention_mask)
        sequence_output = outputs[0]
        logits1 = self.classifier(self.dropout1(sequence_output))
        logits2 = self.classifier(self.dropout2(sequence_output))
        logits3 = self.classifier(self.dropout3(sequence_output))
        logits4 = self.classifier(self.dropout4(sequence_output))
        logits5 = self.classifier(self.dropout5(sequence_output))
        logits = (logits1 + logits2 + logits3 + logits4 + logits5) / 5
        loss = None
        if labels is not None:
            loss_fct = torch.nn.CrossEntropyLoss()
            loss = loss_fct(logits.view(-1, 3), labels.view(-1))
        return logits, loss, {}

    def optimizer_scheduler(self):
        opt = Adam(self.parameters(), lr=self.learning_rate)
        sch = get_linear_schedule_with_warmup(
            opt,
            num_warmup_steps=0.2 * self.num_train_steps,
            num_training_steps=self.num_train_steps,
            last_epoch=-1,
        )
        return opt, sch


class Model6(torch.nn.Module):
    def __init__(self, ckpt, num_train_steps, learning_rate, reduction='mean', warmup_ratio=0):
        super().__init__()
        self.backbone = AutoModel.from_pretrained(ckpt)
        self.dropout1 = StableDropout(0.1)
        self.dropout2 = StableDropout(0.2)
        self.dropout3 = StableDropout(0.3)
        self.dropout4 = StableDropout(0.4)
        self.dropout5 = StableDropout(0.5)
        self.classifier = torch.nn.Linear(self.backbone.config.hidden_size, 3)
        self.num_train_steps = num_train_steps
        self.learning_rate = learning_rate
        self.loss_fct = torch.nn.CrossEntropyLoss(reduction=reduction)
        self.warmup_ratio = warmup_ratio

    def forward(self, input_ids=None, attention_mask=None, labels=None):
        outputs = self.backbone(input_ids=input_ids, attention_mask=attention_mask)
        sequence_output = outputs[0]
        logits1 = self.classifier(self.dropout1(sequence_output))
        logits2 = self.classifier(self.dropout2(sequence_output))
        logits3 = self.classifier(self.dropout3(sequence_output))
        logits4 = self.classifier(self.dropout4(sequence_output))
        logits5 = self.classifier(self.dropout5(sequence_output))
        logits = (logits1 + logits2 + logits3 + logits4 + logits5) / 5
        loss = None
        if labels is not None:
            loss = self.loss_fct(logits.view(-1, 3), labels.view(-1))
        return logits, loss, {}

    def optimizer_scheduler(self):
        opt = RAdam(self.parameters(), lr=self.learning_rate)
        sch = get_linear_schedule_with_warmup(
            opt,
            num_warmup_steps=int(self.warmup_ratio*self.num_train_steps),
            num_training_steps=self.num_train_steps,
            last_epoch=-1,
        )
        return opt, sch

# model 6 + diff lr
class Model8(torch.nn.Module):
    def __init__(self, ckpt, num_train_steps, lr, lr_head=None, reduction='mean', warmup_ratio=0):
        super().__init__()
        self.backbone = AutoModel.from_pretrained(ckpt)
        self.dropout1 = StableDropout(0.1)
        self.dropout2 = StableDropout(0.2)
        self.dropout3 = StableDropout(0.3)
        self.dropout4 = StableDropout(0.4)
        self.dropout5 = StableDropout(0.5)
        self.classifier = torch.nn.Linear(self.backbone.config.hidden_size, 3)
        self.num_train_steps = num_train_steps
        self.lr = lr
        if lr_head:
            self.lr_head = lr_head
        else:
            self.lr_head = lr
        self.loss_fct = torch.nn.CrossEntropyLoss(reduction=reduction)
        self.warmup_ratio = warmup_ratio

    def forward(self, input_ids=None, attention_mask=None, labels=None):
        outputs = self.backbone(input_ids=input_ids, attention_mask=attention_mask)
        sequence_output = outputs[0]
        logits1 = self.classifier(self.dropout1(sequence_output))
        logits2 = self.classifier(self.dropout2(sequence_output))
        logits3 = self.classifier(self.dropout3(sequence_output))
        logits4 = self.classifier(self.dropout4(sequence_output))
        logits5 = self.classifier(self.dropout5(sequence_output))
        logits = (logits1 + logits2 + logits3 + logits4 + logits5) / 5
        loss = None
        if labels is not None:
            loss = self.loss_fct(logits.view(-1, 3), labels.view(-1))
        return logits, loss, {}

    def optimizer_scheduler(self):
        optimizer_parameters = [
            {
                "params": [p for n, p in self.backbone.named_parameters()],
                "lr": self.lr,
            },
            {
                "params": [p for n, p in self.classifier.named_parameters()],
                "lr": self.lr_head,
            },
            ]
        opt = RAdam(optimizer_parameters)
        sch = get_linear_schedule_with_warmup(
            opt,
            num_warmup_steps=int(self.warmup_ratio*self.num_train_steps),
            num_training_steps=self.num_train_steps,
            last_epoch=-1,
        )
        return opt, sch


# Model8 + single dropout
class Model9(torch.nn.Module):
    def __init__(self, ckpt, num_train_steps, lr, lr_head=None, reduction='mean', warmup_ratio=0):
        super().__init__()
        self.backbone = AutoModel.from_pretrained(ckpt)
        self.dropout = StableDropout(0.1)
        self.classifier = torch.nn.Linear(self.backbone.config.hidden_size, 3)
        self.num_train_steps = num_train_steps
        self.lr = lr
        if lr_head:
            self.lr_head = lr_head
        else:
            self.lr_head = lr
        self.loss_fct = torch.nn.CrossEntropyLoss(reduction=reduction)
        self.warmup_ratio = warmup_ratio

    def forward(self, input_ids=None, attention_mask=None, labels=None):
        outputs = self.backbone(input_ids=input_ids, attention_mask=attention_mask)
        sequence_output = outputs[0]
        logits = self.classifier(self.dropout(sequence_output))
        loss = None
        if labels is not None:
            loss = self.loss_fct(logits.view(-1, 3), labels.view(-1))
        return logits, loss, {}

    def optimizer_scheduler(self):
        optimizer_parameters = [
            {
                "params": [p for n, p in self.backbone.named_parameters()],
                "lr": self.lr,
            },
            {
                "params": [p for n, p in self.classifier.named_parameters()],
                "lr": self.lr_head,
            },
            ]
        opt = RAdam(optimizer_parameters)
        sch = get_linear_schedule_with_warmup(
            opt,
            num_warmup_steps=int(self.warmup_ratio*self.num_train_steps),
            num_training_steps=self.num_train_steps,
            last_epoch=-1,
        )
        return opt, sch

# model 8 + 8-bit optim
class Model11(torch.nn.Module):
    def __init__(self, ckpt, num_train_steps, lr, lr_head=None, reduction='mean', warmup_ratio=0):
        super().__init__()
        self.backbone = AutoModel.from_pretrained(ckpt)
        self.dropout1 = StableDropout(0.1)
        self.dropout2 = StableDropout(0.2)
        self.dropout3 = StableDropout(0.3)
        self.dropout4 = StableDropout(0.4)
        self.dropout5 = StableDropout(0.5)
        self.classifier = torch.nn.Linear(self.backbone.config.hidden_size, 3)
        self.num_train_steps = num_train_steps
        self.lr = lr
        if lr_head:
            self.lr_head = lr_head
        else:
            self.lr_head = lr
        self.loss_fct = torch.nn.CrossEntropyLoss(reduction=reduction)
        self.warmup_ratio = warmup_ratio

    def forward(self, input_ids=None, attention_mask=None, labels=None):
        outputs = self.backbone(input_ids=input_ids, attention_mask=attention_mask)
        sequence_output = outputs[0]
        logits1 = self.classifier(self.dropout1(sequence_output))
        logits2 = self.classifier(self.dropout2(sequence_output))
        logits3 = self.classifier(self.dropout3(sequence_output))
        logits4 = self.classifier(self.dropout4(sequence_output))
        logits5 = self.classifier(self.dropout5(sequence_output))
        logits = (logits1 + logits2 + logits3 + logits4 + logits5) / 5
        loss = None
        if labels is not None:
            loss = self.loss_fct(logits.view(-1, 3), labels.view(-1))
        return logits, loss, {}

    def optimizer_scheduler(self):
        optimizer_parameters = [
            {
                "params": [p for n, p in self.backbone.named_parameters()],
                "lr": self.lr,
            },
            {
                "params": [p for n, p in self.classifier.named_parameters()],
                "lr": self.lr_head,
            },
            ]
        opt = bnb.optim.Adam8bit(optimizer_parameters)
        sch = get_linear_schedule_with_warmup(
            opt,
            num_warmup_steps=int(self.warmup_ratio*self.num_train_steps),
            num_training_steps=self.num_train_steps,
            last_epoch=-1,
        )
        return opt, sch



    def optimizer_scheduler(self):
        optimizer_parameters = [
            {
                "params": [p for n, p in self.backbone.named_parameters()],
                "lr": self.lr,
            },
            {
                "params": [p for n, p in self.classifier.named_parameters()],
                "lr": self.lr_head,
            },
            {
                "params": [p for n, p in self.rnn.named_parameters()],
                "lr": self.lr_head,
            },
            ]
        opt = RAdam(optimizer_parameters)
        sch = get_linear_schedule_with_warmup(
            opt,
            num_warmup_steps=int(self.warmup_ratio*self.num_train_steps),
            num_training_steps=self.num_train_steps,
            last_epoch=-1,
        )
        return opt, sch


# model 8 + linear all hidden layers
class Model13(torch.nn.Module):
    def __init__(self, ckpt, num_train_steps, lr, lr_head=None, lr_hs_pooler=1e-3, reduction='mean', warmup_ratio=0, hs_pooler_dropout=0.5):
        super().__init__()
        self.config = AutoConfig.from_pretrained(ckpt, output_hidden_states=True)
        self.backbone = AutoModel.from_pretrained(ckpt, config=self.config)
        self.hs_pooler = torch.nn.Linear(self.config.num_hidden_layers, 1)
        self.dropout1 = StableDropout(0.1)
        self.dropout2 = StableDropout(0.2)
        self.dropout3 = StableDropout(0.3)
        self.dropout4 = StableDropout(0.4)
        self.dropout5 = StableDropout(0.5)
        self.classifier = torch.nn.Linear(self.backbone.config.hidden_size, 3)
        self.num_train_steps = num_train_steps
        self.lr = lr
        if lr_head:
            self.lr_head = lr_head
        else:
            self.lr_head = lr
        self.lr_hs_pooler = lr_hs_pooler
        self.loss_fct = torch.nn.CrossEntropyLoss(reduction=reduction)
        self.warmup_ratio = warmup_ratio
        self.hs_pooler_dropout = hs_pooler_dropout

    def forward(self, input_ids=None, attention_mask=None, labels=None):
        outputs = self.backbone(input_ids=input_ids, attention_mask=attention_mask)
        hs = outputs['hidden_states']
        hs_pt = torch.stack(hs[-self.config.num_hidden_layers:], dim=3)
        if random.random() < self.hs_pooler_dropout and self.hs_pooler.training:
            hs_pt[:, :, :, random.randrange(self.config.num_hidden_layers)] = 0
        sequence_output = self.hs_pooler(hs_pt)
        sequence_output = sequence_output.view(sequence_output.shape[0], sequence_output.shape[1], sequence_output.shape[2])
        logits1 = self.classifier(self.dropout1(sequence_output))
        logits2 = self.classifier(self.dropout2(sequence_output))
        logits3 = self.classifier(self.dropout3(sequence_output))
        logits4 = self.classifier(self.dropout4(sequence_output))
        logits5 = self.classifier(self.dropout5(sequence_output))
        logits = (logits1 + logits2 + logits3 + logits4 + logits5) / 5
        loss = None
        if labels is not None:
            loss = self.loss_fct(logits.view(-1, 3), labels.view(-1))
        return logits, loss, {}

    def optimizer_scheduler(self):
        optimizer_parameters = [
            {
                "params": [p for n, p in self.backbone.named_parameters()],
                "lr": self.lr,
            },
            {
                "params": [p for n, p in self.classifier.named_parameters()],
                "lr": self.lr_head,
            },
            {
                "params": [p for n, p in self.hs_pooler.named_parameters()],
                "lr": self.lr_hs_pooler,
            },
            ]
        opt = RAdam(optimizer_parameters)
        sch = get_linear_schedule_with_warmup(
            opt,
            num_warmup_steps=int(self.warmup_ratio*self.num_train_steps),
            num_training_steps=self.num_train_steps,
            last_epoch=-1,
        )
        return opt, sch


# model 11 + freeze embedding
class Model14(torch.nn.Module):
    def __init__(self, ckpt, num_train_steps, lr, lr_head=None, reduction='mean', warmup_ratio=0):
        super().__init__()
        self.backbone = AutoModel.from_pretrained(ckpt)
        self.dropout1 = StableDropout(0.1)
        self.dropout2 = StableDropout(0.2)
        self.dropout3 = StableDropout(0.3)
        self.dropout4 = StableDropout(0.4)
        self.dropout5 = StableDropout(0.5)
        self.classifier = torch.nn.Linear(self.backbone.config.hidden_size, 3)
        self.num_train_steps = num_train_steps
        self.lr = lr
        if lr_head:
            self.lr_head = lr_head
        else:
            self.lr_head = lr
        self.loss_fct = torch.nn.CrossEntropyLoss(reduction=reduction)
        self.warmup_ratio = warmup_ratio

        # freeze emb
        self.emb_param_names = []
        for name, param in self.backbone.embeddings.named_parameters():
            self.emb_param_names.append(name)
            param.requires_grad = False
        print("emb param names:", self.emb_param_names)

    def forward(self, input_ids=None, attention_mask=None, labels=None):
        outputs = self.backbone(input_ids=input_ids, attention_mask=attention_mask)
        sequence_output = outputs[0]
        logits1 = self.classifier(self.dropout1(sequence_output))
        logits2 = self.classifier(self.dropout2(sequence_output))
        logits3 = self.classifier(self.dropout3(sequence_output))
        logits4 = self.classifier(self.dropout4(sequence_output))
        logits5 = self.classifier(self.dropout5(sequence_output))
        logits = (logits1 + logits2 + logits3 + logits4 + logits5) / 5
        loss = None
        if labels is not None:
            loss = self.loss_fct(logits.view(-1, 3), labels.view(-1))
        return logits, loss, {}

    def optimizer_scheduler(self):
        optimizer_parameters = [
            {
                "params": [p for n, p in self.backbone.named_parameters() if n not in self.emb_param_names],
                "lr": self.lr,
            },
            {
                "params": [p for n, p in self.classifier.named_parameters()],
                "lr": self.lr_head,
            },
            ]
        opt = bnb.optim.Adam8bit(optimizer_parameters)
        sch = get_linear_schedule_with_warmup(
            opt,
            num_warmup_steps=int(self.warmup_ratio*self.num_train_steps),
            num_training_steps=self.num_train_steps,
            last_epoch=-1,
        )
        return opt, sch
