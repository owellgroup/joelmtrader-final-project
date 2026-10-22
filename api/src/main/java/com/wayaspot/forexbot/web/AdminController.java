package com.wayaspot.forexbot.web;

import com.wayaspot.forexbot.entity.AdminUser;
import com.wayaspot.forexbot.repo.AdminUserRepository;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/admins")
@PreAuthorize("hasRole('SUPER_ADMIN')")
public class  AdminController {
    public record CreateRequest(@NotBlank String username, @NotBlank @Size(min = 8, message = "must be at least 8 characters") String password) { }
    public record UpdateRequest(String username, String password, Boolean enabled) { }

    private final AdminUserRepository users;
    private final PasswordEncoder encoder;

    public AdminController(AdminUserRepository users, PasswordEncoder encoder) {
        this.users = users;
        this.encoder = encoder;
    }
    //fff

    @GetMapping
    public List<Map<String, Object>> list() {
        return users.findAll().stream().map(AuthController::view).toList();
    }

    @PostMapping
    public Map<String, Object> create(@Valid @RequestBody CreateRequest r) {
        String name = r.username().trim();
        if (users.existsByUsername(name)) throw new ResponseStatusException(HttpStatus.CONFLICT, "Username already exists");
        AdminUser u = new AdminUser();
        u.setUsername(name);
        u.setPasswordHash(encoder.encode(r.password()));
        u.setRole("ADMIN");
        return AuthController.view(users.save(u));
    }

    @PutMapping("/{id}")
    public Map<String, Object> update(@PathVariable Long id, @RequestBody UpdateRequest r, Authentication auth) {
        AdminUser u = users.findById(id).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Admin not found"));
        if (r.username() != null && !r.username().isBlank() && !r.username().trim().equals(u.getUsername())) {
            if (users.existsByUsername(r.username().trim())) throw new ResponseStatusException(HttpStatus.CONFLICT, "Username already exists");
            u.setUsername(r.username().trim());
        }
        if (r.password() != null && !r.password().isBlank()) {
            if (r.password().length() < 8) throw new IllegalArgumentException("Password must be at least 8 characters");
            u.setPasswordHash(encoder.encode(r.password()));
        }
        if (r.enabled() != null) {
            if ("SUPER_ADMIN".equals(u.getRole()) && !r.enabled())
                throw new IllegalArgumentException("The super admin cannot be disabled");
            u.setEnabled(r.enabled());
        }
        return AuthController.view(users.save(u));
    }

    @DeleteMapping("/{id}")
    public Map<String, Object> delete(@PathVariable Long id, Authentication auth) {
        AdminUser u = users.findById(id).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Admin not found"));
        if ("SUPER_ADMIN".equals(u.getRole())) throw new IllegalArgumentException("The super admin cannot be deleted");
        if (u.getUsername().equals(auth.getName())) throw new IllegalArgumentException("You cannot delete yourself");
        users.delete(u);
        return Map.of("deleted", true);
    }
}
