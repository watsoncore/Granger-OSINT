"""A queued GUI job can acknowledge completion without blocking QWebChannel."""


class DeferredReply:
    def __init__(self):
        self.finished=False
        self.value=None
        self.error=None
        self.callbacks=[]

    def subscribe(self,callback):
        if self.finished:callback(self.value,self.error)
        else:self.callbacks.append(callback)

    def resolve(self,value=None,error=None):
        if self.finished:return
        self.finished=True;self.value=value;self.error=error
        callbacks,self.callbacks=self.callbacks,[]
        for callback in callbacks:callback(value,error)
