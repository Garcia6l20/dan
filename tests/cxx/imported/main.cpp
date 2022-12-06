#include <iostream>
#include <semaphore.h>

int main() {
    sem_t sem;
    return sem_init(&sem, 0, 0);
}
