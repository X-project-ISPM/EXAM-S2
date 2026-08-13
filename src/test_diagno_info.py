from diagnostic import extraire_diagnostic

# Cas riche en infos
r1 = extraire_diagnostic(
    "Mon imprimante HP du 3e étage (IMP-045) ne répond plus depuis ce matin, "
    "j'ai déjà essayé de la redémarrer."
)
print(r1)
# Attendu : equipement="IMP-045" ou similaire, moment_apparition="ce matin",
# manipulations_effectuees rempli, informations_manquantes courte ou vide

# Cas incomplet (scénario 3)
r2 = extraire_diagnostic("Ça ne marche plus.")
print(r2)
# Attendu : la plupart des champs à None, informations_manquantes non vide