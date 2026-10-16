i am  buliding a resturant order managament ai agent system using langrqaph
i will explainyou everything  very clearly what i want and what is the architecture.i will also explain te nodes states and edges for the langgrapgh. in the end i will give you 
testcases for simulate and tell me wether they pass or fail.

the rough architecture :
There will be a user when the code  runs the user will give an order this will be taken as as input which i will type and this order should go to thew LLM
The order as of now should contain dish and required quantity.
for simplicity purpose for now you can take the order as per your wish dish and whatever availabulity  the user want the llm has to extract the name and quantity from the user input .
If the user input is unrelated to the food and brevages the llms should not  entertain it and tell the user that it is an ai agent of restureant for food orderinng.

once the LLM has orderd the dish and quantity 
it will send thet to a node called order_confirm 
the task of this order_confirm is too look at the menu (you can decide take any resturant menu ).
Then the node will decide one of the 3 cases:
1. order available 
2. partially available (means quantity is not sufficient ) 
3. not available at all (dish being not available in the menu or quantity is zero)

it will put this in the Status of the state (i will tell you  the exact content of the langgraph state as well)

once the llm reciever this :
if  the ststus is confirmed(means full available) it should call another node called Cook.
if status is not or partially avaialable is should again prompt user to decide :
    the user can either place a new order or can confirm ih he want to go ahead wiht partial order

This order retry limited to 3 attempts( meaning after 3 attempts the user is not satisfied the system will copme to the end node).

Now when teh cook node is called there can be 2 cases;
either the cook is done then the status will be Ready.
and if cook fails (we can use a probability function  ). give 35% chances of fails and 75% cances of sucess

if cook fails one moe attemp should be allowed to him to get the sucess.If the cook fails  evern after these then the LLM hsould issue a appology to user and comews to the END state.
if the cook succeds, the status will be ready and the next node will bw called serve.

A similar to the cook this also have 2 cases :
server failed 
server success

this also has 2 retry attempts .If the serve fails  evern after these then the LLM hsould issue a appology to user and comews to the END state.
if the serve fails 2 times then the 1lm should issue a aplogy to the user and come to END state

if the serve suceeds the status should bceomc ocmplete the 1lm should uissue a message to the user saying your oder is complete
if serve fails then cook should becalled one more time to retruy.
Note that if cok has exhausted its retrey attempts then it should not cook again and 1lm should issue an apology and come to end state

Now the state of lagragph
there should be a annotated message be 1lm and user

there should be order details
dish name as str
required quantuty as int
available quantity as string
order_conform will write the available quantuty by readibng the menu
the llm should get to know the order confrm status by reading the state
if a dish is not avilabel in the mnu then orderconform should write 0 as avail quantity

then there should be status
each node will update the status as specifed in the above rules
then order retry attemps which are 3
cook retry attemnpts which are 2
serve retry attempts which are 2
each time a filure haappend and a node is retrying it should diecreent the couner
if any retry counter becomes 0 it means it is over. LLm should unbdersatnd wehter it has to give a retry or isue appology by reading this counter \in the end there should be final ; result wheter the order was completed or not 


write the code and ask if there any open questions from yu side thenask
i will give you some test senarios to test later.
