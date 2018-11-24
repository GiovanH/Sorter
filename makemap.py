# def makeMappings(lst):
#     keys = {i: i.split('\\')[-2].lower() for i in lst}
#     again = True
#     while again:
#         again = False
#         for i in range(0, len(lst)):
#             if keys[lst[i]][:-1] != "" and keys[lst[i]][:-1] not in keys.values():
#                 keys[lst[i]] = keys[lst[i]][:-1]
#                 again = True
#     map_prime = {keys[i]: i for i in lst}
#     print(map_prime)
#     return map_prime


def makeMappings(lst):
    vals = [i.split('\\')[-2].lower() for i in lst]
    done = False
    extent = 0
    while not done:
        extent += 1
        prefixes = [var[0:extent] for var in vals]
        if len(set(prefixes)) == len(prefixes):
            done = True

    map_prime = {prefixes[i]: lst[i] for i in range(0, len(lst))}
    print(map_prime)
    return map_prime


if __name__ == "__main__":
    print(makeMappings(
        [".\\{}\\".format(i) for i in ["Ampora", "Carapace", "Cherub", "Couples", "Poly", "Pyrope"]]))
