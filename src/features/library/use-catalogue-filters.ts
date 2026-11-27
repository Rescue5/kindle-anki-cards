import { useState } from "react";
import { defaultCatalogueFilters, type CatalogueFilters } from "./catalogue-selectors";

export function useCatalogueFilters() {
  const [filters, setFilters] = useState<CatalogueFilters>(defaultCatalogueFilters);
  return { filters, setFilters };
}
