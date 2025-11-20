import os
import json
from pathlib import Path


class JavaModuleGenerator:
    def __init__(self, config_file):
        with open(config_file, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        self.base_path = self.config.get('base_path', 'src/main/java')
        self.package_base = self.config.get('package_base', 'com.kanstad.task')
        self.modules_base_path = self.config.get('modules_base_path', '/example/project')
        # Flag para evitar crear el paquete exceptions más de una vez por ejecución
        self.exceptions_created = False

    def create_entity(self, entity_config):
        """Genera el archivo de entidad JPA"""
        entity_name = entity_config['name']
        fields = entity_config['fields']
        schema = entity_config.get('schema', 'configuracion')
        table_name = entity_config.get('table_name', self._to_snake_case(entity_name))
        
        package = f"{self.package_base}.{entity_name.lower()}"
        class_name = self._capitalize(entity_name)
        
        # Importaciones base
        imports = set([
            "jakarta.persistence.Column",
            "jakarta.persistence.Entity",
            "jakarta.persistence.GeneratedValue",
            "jakarta.persistence.GenerationType",
            "jakarta.persistence.Id",
            "jakarta.persistence.SequenceGenerator",
            "jakarta.persistence.Table",
            "lombok.AllArgsConstructor",
            "lombok.Builder",
            "lombok.Data",
            "lombok.NoArgsConstructor"
        ])
        
        # Agregar imports según los campos
        for field in fields:
            if field.get('type') == 'relation':
                imports.add("jakarta.persistence.JoinColumn")
                imports.add("jakarta.persistence.ManyToOne")
                rel_class = field['relation_class']
                rel_package = field.get('relation_package', f"{self.package_base}.{rel_class.lower()}.{rel_class}")
                imports.add(rel_package)
        
        imports_str = "\n".join(sorted([f"import {imp};" for imp in imports]))
        
        id_prefix = entity_config.get('id_prefix', entity_name[:3].lower())
        # Generar campos
        field_definitions = self._generate_entity_fields(fields, entity_name,id_prefix)
        
        # Secuencia del ID
        
        sequence_name = f"{schema}.{table_name}_{id_prefix}_id_seq"
        
        content = f"""package {package};

{imports_str}

@Entity
@Table(name = "{table_name}", schema = "{schema}")
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class {class_name} {{

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "{table_name}_id_seq")
    @SequenceGenerator(name = "{table_name}_id_seq", sequenceName = "{sequence_name}", allocationSize = 1)
    @Column(name = "{id_prefix}_id")
    private Long id;

{field_definitions}
}}
"""
        return content

    def create_dto(self, entity_config):
        """Genera el archivo DTO"""
        entity_name = entity_config['name']
        fields = entity_config['fields']
        
        package = f"{self.package_base}.{entity_name.lower()}.dto"
        class_name = f"{self._capitalize(entity_name)}DTO"
        
        imports = """import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.Setter;
import lombok.NoArgsConstructor;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;"""

        field_definitions = self._generate_dto_fields(fields)
        
        content = f"""package {package};

{imports}

@Getter
@Setter
@AllArgsConstructor
@NoArgsConstructor
public class {class_name} {{

    private Long id;
{field_definitions}
}}
"""
        return content

    def create_mapper(self, entity_config):
        """Genera el archivo Mapper con MapStruct"""
        entity_name = entity_config['name']
        fields = entity_config['fields']
        
        package = f"{self.package_base}.{entity_name.lower()}.mappers"
        entity_class = self._capitalize(entity_name)
        dto_class = f"{entity_class}DTO"
        
        # Generar mappings para relaciones
        to_dto_mappings = []
        to_entity_mappings = []
        
        for field in fields:
            if field.get('type') == 'relation':
                field_name = field['name']
                to_dto_mappings.append(f'@Mapping(source = "{field_name}.id", target = "{field_name}Id")')
                to_entity_mappings.append(f'@Mapping(source = "{field_name}Id", target = "{field_name}.id")')
        
        to_dto_mapping_str = "\n    ".join(to_dto_mappings) if to_dto_mappings else ""
        to_entity_mapping_str = "\n    ".join(to_entity_mappings) if to_entity_mappings else ""
        
        to_dto_decorator = f"\n    {to_dto_mapping_str}\n    " if to_dto_mapping_str else "\n    "
        to_entity_decorator = f"\n    {to_entity_mapping_str}\n    " if to_entity_mapping_str else "\n    "
        
        content = f"""package {package};

import org.mapstruct.Mapper;
import org.mapstruct.Mapping;
import {self.package_base}.{entity_name.lower()}.{entity_class};
import {self.package_base}.{entity_name.lower()}.dto.{dto_class};

@Mapper(componentModel = "spring")
public interface {entity_class}Mapper {{
{to_dto_decorator}{dto_class} toDto({entity_class} {entity_name.lower()});
{to_entity_decorator}{entity_class} toEntity({dto_class} {entity_name.lower()}DTO);
}}
"""
        return content

    def create_repository(self, entity_config):
        """Genera el archivo Repository"""
        entity_name = entity_config['name']
        package = f"{self.package_base}.{entity_name.lower()}.repositories"
        entity_class = self._capitalize(entity_name)
        
        content = f"""package {package};

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;
import {self.package_base}.{entity_name.lower()}.{entity_class};

@Repository
public interface {entity_class}Repository extends JpaRepository<{entity_class}, Long> {{

}}
"""
        return content

    def create_service(self, entity_config):
        """Genera el archivo Service"""
        entity_name = entity_config['name']
        fields = entity_config['fields']
        
        package = f"{self.package_base}.{entity_name.lower()}.services"
        entity_class = self._capitalize(entity_name)
        dto_class = f"{entity_class}DTO"
        var_name = entity_name[0].lower() + entity_name[1:]
        
        # Importaciones adicionales para relaciones
        relation_imports = []
        relation_repositories = []
        
        for field in fields:
            if field.get('type') == 'relation':
                rel_class = field['relation_class']
                rel_lower = rel_class.lower()
                relation_imports.append(f"import {self.package_base}.{rel_lower}.{rel_class};")
                relation_imports.append(f"import {self.package_base}.{rel_lower}.repositories.{rel_class}Repository;")
                relation_repositories.append(f"    private final {rel_class}Repository {rel_lower}Repository;")
        
        relation_imports_str = "\n".join(sorted(set(relation_imports)))
        relation_repos_str = "\n".join(relation_repositories)
        
        # Validaciones y seteo de relaciones en create
        create_validations = self._generate_service_validations(fields, entity_name)
        
        # Validaciones en update
        update_validations = self._generate_service_validations(fields, entity_name)
        update_sets = self._generate_service_updates(fields, entity_class)
        
        content = f"""package {package};

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import {self.package_base}.exception.NotFoundException;
import {self.package_base}.{entity_name.lower()}.{entity_class};
import {self.package_base}.{entity_name.lower()}.dto.{dto_class};
import {self.package_base}.{entity_name.lower()}.mappers.{entity_class}Mapper;
import {self.package_base}.{entity_name.lower()}.repositories.{entity_class}Repository;
{relation_imports_str}

@Service
@RequiredArgsConstructor
public class {entity_class}Service {{

    private final {entity_class}Repository {var_name}Repository;
    private final {entity_class}Mapper {var_name}Mapper;
{relation_repos_str}

    public Page<{dto_class}> getAll(Pageable pageable) {{
        return {var_name}Repository.findAll(pageable)
                .map({var_name}Mapper::toDto);
    }}

    public {dto_class} findByIdOrThrow(Long id) {{
        return {var_name}Repository.findById(id)
                .map({var_name}Mapper::toDto)
                .orElseThrow(() -> new NotFoundException("{var_name}.not-found", id));
    }}

    public {dto_class} create({dto_class} dto) {{
{create_validations}
        {entity_class} {var_name} = {var_name}Mapper.toEntity(dto);
        return {var_name}Mapper.toDto({var_name}Repository.save({var_name}));
    }}

    public {dto_class} update(Long id, {dto_class} dto) {{
        {entity_class} existing{entity_class} = {var_name}Repository.findById(id)
                .orElseThrow(() -> new NotFoundException("{var_name}.not-found", id));
{update_validations}
{update_sets}
        return {var_name}Mapper.toDto({var_name}Repository.save(existing{entity_class}));
    }}

    public void delete(Long id) {{
        if (!{var_name}Repository.existsById(id)) {{
            throw new NotFoundException("{var_name}.not-found", id);
        }}
        {var_name}Repository.deleteById(id);
    }}
}}
"""
        return content

    def create_controller(self, entity_config):
        """Genera el archivo Controller"""
        entity_name = entity_config['name']
        endpoint = entity_config.get('endpoint', self._to_kebab_case(entity_name))
        
        package = f"{self.package_base}.{entity_name.lower()}.controller"
        entity_class = self._capitalize(entity_name)
        dto_class = f"{entity_class}DTO"
        service_class = f"{entity_class}Service"
        var_name = entity_name[0].lower() + entity_name[1:]
        
        content = f"""package {package};

import java.net.URI;
import jakarta.validation.Valid;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.UriComponentsBuilder;
import lombok.RequiredArgsConstructor;
import {self.package_base}.{entity_name.lower()}.dto.{dto_class};
import {self.package_base}.{entity_name.lower()}.services.{service_class};

@RestController
@RequestMapping("/api/{endpoint}")
@RequiredArgsConstructor
public class {entity_class}Controller {{

    private final {service_class} {var_name}Service;

    @GetMapping
    public ResponseEntity<Page<{dto_class}>> getAll{entity_class}s(Pageable pageable) {{
        return ResponseEntity.ok({var_name}Service.getAll(pageable));
    }}

    @GetMapping("/{{id}}")
    public ResponseEntity<{dto_class}> find{entity_class}ById(@PathVariable Long id) {{
        return ResponseEntity.ok({var_name}Service.findByIdOrThrow(id));
    }}

    @PostMapping
    public ResponseEntity<{dto_class}> create{entity_class}(@Valid @RequestBody {dto_class} {var_name}DTO,
                                              UriComponentsBuilder uriComponentsBuilder) {{
        {dto_class} created = {var_name}Service.create({var_name}DTO);
        URI location = uriComponentsBuilder.path("/api/{endpoint}/{{id}}")
                .buildAndExpand(created.getId())
                .toUri();
        return ResponseEntity.created(location).body(created);
    }}

    @PutMapping("/{{id}}")
    public ResponseEntity<{dto_class}> update{entity_class}(@PathVariable Long id,
                                              @Valid @RequestBody {dto_class} {var_name}DTO) {{
        return ResponseEntity.ok({var_name}Service.update(id, {var_name}DTO));
    }}

    @DeleteMapping("/{{id}}")
    public ResponseEntity<Void> delete{entity_class}(@PathVariable Long id) {{
        {var_name}Service.delete(id);
        return ResponseEntity.noContent().build();
    }}
}}
"""
        return content

    def _generate_entity_fields(self, fields, entity_name, id_prefix):
        """Genera los campos de la entidad"""
        if not id_prefix:
            id_prefix = entity_name[:3].lower()
        field_lines = []
        
        for field in fields:
            if field.get('type') == 'relation':
                print(field.get('referenced_column', 'id'))
                field_lines.append(f"""
    @ManyToOne
    @JoinColumn(name = "{id_prefix}_{field['column']}", referencedColumnName = "{field.get('referenced_column', 'id')}")
    private {field['relation_class']} {field['name']};""")
            else:
                column_name = f"{id_prefix}_{field['column']}"
                print(column_name)
                print(id_prefix)
                field_lines.append(f"""
    @Column(name = "{column_name}")
    private {field['java_type']} {field['name']};""")
        
        return "".join(field_lines)

    def _generate_dto_fields(self, fields):
        """Genera los campos del DTO"""
        field_lines = []
        
        for field in fields:
            annotations = []
            
            if field.get('required'):
                if field.get('type') == 'relation':
                    annotations.append(f'@NotNull(message = "El {field["name"]} no puede ser nulo")')
                else:
                    annotations.append(f'@NotBlank(message = "El {field["name"]} no puede estar en blanco")')
            
            if field.get('max_length') and field.get('type') != 'relation':
                annotations.append(f'@Size(max = {field["max_length"]}, message = "El {field["name"]} no puede tener más de {field["max_length"]} caracteres")')
            
            annotations_str = "\n    ".join(annotations)
            if annotations_str:
                annotations_str = "\n    " + annotations_str
            
            if field.get('type') == 'relation':
                field_lines.append(f'{annotations_str}\n    private Long {field["name"]}Id;')
            else:
                field_lines.append(f'{annotations_str}\n    private {field["java_type"]} {field["name"]};')
        
        return "".join(field_lines)

    def _generate_service_validations(self, fields, entity_name):
        """Genera validaciones de relaciones en el servicio"""
        validations = []
        
        for field in fields:
            if field.get('type') == 'relation':
                rel_class = field['relation_class']
                rel_lower = rel_class.lower()
                field_name = field['name']
                
                validations.append(f"""        {rel_class} {field_name} = {rel_lower}Repository.findById(dto.get{self._capitalize(field_name)}Id())
                .orElseThrow(() -> new NotFoundException("{rel_lower}.not-found", dto.get{self._capitalize(field_name)}Id()));""")
        
        return "\n".join(validations) + "\n" if validations else ""

    def _generate_service_updates(self, fields,entity_class):
        """Genera actualizaciones de campos en update"""
        updates = []
        
        for field in fields:
            field_name = field['name']
            cap_name = self._capitalize(field_name)
            
            if field.get('type') == 'relation':
                updates.append(f"        existing{entity_class}.set{cap_name}({field_name});")
            else:
                updates.append(f"        existing{entity_class}.set{cap_name}(dto.get{cap_name}());")
        
        return "\n".join(updates)

    def _capitalize(self, text):
        return text[0].upper() + text[1:] if text else text

    def _to_snake_case(self, text):
        result = []
        for i, c in enumerate(text):
            if c.isupper() and i > 0:
                result.append('_')
            result.append(c.lower())
        return ''.join(result)

    def _to_kebab_case(self, text):
        snake = self._to_snake_case(text)
        return snake.replace('_', '-')

    def generate_module(self, entity_config, output_base_path=None):
        """Genera todos los archivos del módulo"""
        if output_base_path is None:
            output_base_path = self.base_path
            
        # Asegurarse de generar el paquete de exceptions una sola vez (idempotente)
        if not self.exceptions_created:
            self.create_exceptions(output_base_path)

        entity_name = entity_config['name']
        # Asegurarse de crear/actualizar messages.properties por cada módulo (idempotente)
        try:
            self.create_or_update_messages(entity_name, output_base_path)
        except Exception as e:
            print(f"! Warning: no se pudo actualizar messages.properties: {e}")
        entity_path = f"{output_base_path}{self.modules_base_path}/{entity_name.lower()}"
        
        paths = {
            'entity': entity_path,
            'dto': f"{entity_path}/dto",
            'mapper': f"{entity_path}/mappers",
            'repository': f"{entity_path}/repositories",
            'service': f"{entity_path}/services",
            'controller': f"{entity_path}/controller"
        }
        
        # Crear directorios
        for path in paths.values():
            Path(path).mkdir(parents=True, exist_ok=True)
        
        # Generar archivos
        class_name = self._capitalize(entity_name)
        files = {
            f"{paths['entity']}/{class_name}.java": self.create_entity(entity_config),
            f"{paths['dto']}/{class_name}DTO.java": self.create_dto(entity_config),
            f"{paths['mapper']}/{class_name}Mapper.java": self.create_mapper(entity_config),
            f"{paths['repository']}/{class_name}Repository.java": self.create_repository(entity_config),
            f"{paths['service']}/{class_name}Service.java": self.create_service(entity_config),
            f"{paths['controller']}/{class_name}Controller.java": self.create_controller(entity_config)
        }
        
        # Escribir archivos
        for file_path, content in files.items():
            # No sobreescribir archivos si ya existen (idempotencia)
            if os.path.exists(file_path):
                print(f"✓ Existe (omitido): {file_path}")
                continue
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✓ Creado: {file_path}")

        # Marcar que ya intentamos crear exceptions para esta ejecución
        self.exceptions_created = True

    def create_or_update_messages(self, entity_name, output_base_path=None):
        """Crea o actualiza src/main/resources/messages.properties añadiendo
        la clave '<entity>.not-found' con el mensaje en español. No duplica entradas.
        """
        if output_base_path is None:
            output_base_path = self.base_path

        # Intentar deducir la ruta 'src/main/resources' a partir de output_base_path
        base = Path(output_base_path)
        resources_path = None
        try:
            parts = list(base.parts)
            if 'src' in parts:
                idx = parts.index('src')
                project_root = Path(*parts[:idx]) if idx > 0 else Path('.')
                resources_path = project_root / 'src' / 'main' / 'resources'
            else:
                # Fallback: asumir estructura estándar
                resources_path = Path('src') / 'main' / 'resources'
        except Exception:
            resources_path = Path('src') / 'main' / 'resources'

        resources_path.mkdir(parents=True, exist_ok=True)
        messages_file = resources_path / 'messages.properties'

        key = f"{entity_name.lower()}.not-found"
        message = f"El {entity_name.lower()} con id {{0}} no existe."
        entry = f"{key}={message}"

        if messages_file.exists():
            with open(messages_file, 'r', encoding='utf-8') as f:
                lines = [ln.rstrip('\n') for ln in f]
            # comprobar existencia de la clave (ignorando espacios y comentarios)
            exists = any(ln.strip().startswith(f"{key}=") for ln in lines if ln.strip() and not ln.strip().startswith('#'))
            if exists:
                print(f"✓ Mensaje existente (omitido): {messages_file} -> {key}")
                return
            # añadir nueva entrada al final
            with open(messages_file, 'a', encoding='utf-8') as f:
                # asegurar nueva línea antes de añadir si el archivo no termina con newline
                if lines and not lines[-1].endswith('\n'):
                    f.write('\n')
                f.write(entry + '\n')
            print(f"✓ Añadido mensaje a: {messages_file} -> {key}")
        else:
            with open(messages_file, 'w', encoding='utf-8') as f:
                f.write(entry + '\n')
            print(f"✓ Creado: {messages_file} con clave {key}")

    def create_exceptions(self, output_base_path=None):
        """Crea el paquete de exceptions con NotFoundException y GlobalExceptionHandler.
        No sobrescribe archivos existentes.
        """
        if output_base_path is None:
            output_base_path = self.base_path

        exceptions_path = f"{output_base_path}{self.modules_base_path}/exception"
        Path(exceptions_path).mkdir(parents=True, exist_ok=True)

        package = f"{self.package_base}.exception"

        not_found_content = '''package {PACKAGE};

public class NotFoundException extends RuntimeException {
    private final String key;
    private final Object id;

    public NotFoundException(String key, Object id) {
        super(String.format("%s: %s", key, id));
        this.key = key;
        this.id = id;
    }

    public String getKey() {
        return key;
    }

    public Object getId() {
        return id;
    }
}
'''.replace('{PACKAGE}', package)

        handler_content = '''package {PACKAGE};

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import lombok.extern.slf4j.Slf4j;

@RestControllerAdvice
@Slf4j
public class GlobalExceptionHandler {

    @ExceptionHandler(NotFoundException.class)
    public ResponseEntity<String> handleNotFound(NotFoundException ex) {
        log.warn("NotFound: {}", ex.getMessage());
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(ex.getMessage());
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<String> handleOther(Exception ex) {
        log.error("Unhandled exception", ex);
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body("Internal server error");
    }
}
'''.replace('{PACKAGE}', package)

        files = {
            f"{exceptions_path}/NotFoundException.java": not_found_content,
            f"{exceptions_path}/GlobalExceptionHandler.java": handler_content,
        }

        for file_path, content in files.items():
            if os.path.exists(file_path):
                print(f"✓ Existe (omitido): {file_path}")
                continue
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✓ Creado: {file_path}")


def create_example_config():
    """Crea un archivo de configuración de ejemplo"""
    config = {
        "base_path": "src/main/java",
        "package_base": "com.kanstad.task",
        "entities": [
            {
                "name": "SubSistema",
                "table_name": "sub_sistema",
                "schema": "configuracion",
                "id_prefix": "sus",
                "endpoint": "sub-sistema",
                "fields": [
                    {
                        "name": "nombre",
                        "java_type": "String",
                        "column": "nombre",
                        "required": True,
                        "max_length": 50
                    },
                    {
                        "name": "descripcion",
                        "java_type": "String",
                        "column": "descripcion",
                        "required": False,
                        "max_length": 255
                    },
                    {
                        "name": "sistema",
                        "type": "relation",
                        "relation_class": "Sistema",
                        "column": "sistema_id",
                        "referenced_column": "sis_id",
                        "required": True
                    },
                    {
                        "name": "estado",
                        "type": "relation",
                        "relation_class": "Estado",
                        "column": "estado_id",
                        "referenced_column": "est_id",
                        "required": True
                    }
                ]
            },
            {
                "name": "Producto",
                "table_name": "producto",
                "schema": "configuracion",
                "id_prefix": "pro",
                "endpoint": "producto",
                "fields": [
                    {
                        "name": "codigo",
                        "java_type": "String",
                        "column": "codigo",
                        "required": True,
                        "max_length": 20
                    },
                    {
                        "name": "nombre",
                        "java_type": "String",
                        "column": "nombre",
                        "required": True,
                        "max_length": 100
                    },
                    {
                        "name": "precio",
                        "java_type": "Double",
                        "column": "precio",
                        "required": True
                    },
                    {
                        "name": "categoria",
                        "type": "relation",
                        "relation_class": "Categoria",
                        "column": "categoria_id",
                        "required": True
                    }
                ]
            }
        ]
    }
    return config


if __name__ == "__main__":
    config_file = "automatizacion/module_config.json"
    
    # Crear archivo de configuración de ejemplo si no existe
    if not os.path.exists(config_file):
        config = create_example_config()
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print(f"✓ Archivo de configuración creado: {config_file}")
        print(f"\nEdita el archivo '{config_file}' con tus entidades y ejecuta de nuevo.\n")
    else:
        # Generar módulos desde la configuración
        print(f"Leyendo configuración desde: {config_file}\n")
        generator = JavaModuleGenerator(config_file)
        
        for entity_config in generator.config.get('entities', []):
            print(f"Generando módulo para: {entity_config['name']}")
            print("=" * 60)
            generator.generate_module(entity_config)
            print()
        
        print("✓ Todos los módulos han sido generados exitosamente!")