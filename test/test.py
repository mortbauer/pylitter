import numpy as np#>
from matplotlib import pyplot as plt#>

## Some example file
a = 2
b = a * 4 +5
c = a +b/5
b
#a = {[a]} is an important variable
x = np.arange(0,1,0.01)#>
x
plt.plot(x,np.sin(x));#:sinus

#i can use the figure later as well Figure \ref{{sinus}}

plt.clf()#>
plt.plot(x,np.cos(x))#:cos
plt.plot(x,np.sin(x))#:cos_sin: sinus und cosinus

#i can use the figure later as well Figure \ref{{cos_sin}}
